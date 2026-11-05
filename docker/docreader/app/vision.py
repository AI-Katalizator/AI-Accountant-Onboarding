# -*- coding: utf-8 -*-
"""Скан без текстового слоя: pypdfium2 рисует страницы -> Ollama (qwen2.5vl) -> JSON по схеме определения.

Задание для модели = prompt.md из определения (ScanReader, MIT) + наши общие правила.
Ответ ограничен JSON-схемой (Ollama structured outputs), затем проверяется pydantic-схемой
определения; ошибки схемы (например, неверная контрольная цифра ИНН) уходят в checks/warnings.
"""
import base64
import importlib
import io
import json
import os
import re
import time
import urllib.request
from typing import List, Optional

import pypdfium2 as pdfium

from .classify import DEF_DIR, TYPE_DEF
from .header import contract_from, payment_docs_from
from .reader import EMPTY, doc_rate, finish, vat_mode_of
from .util import clean, money, norm_date, norm_rate, num

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
MODEL = os.getenv("VISION_MODEL", "qwen2.5vl:7b-16k")
NUM_CTX = int(os.getenv("VISION_NUM_CTX", "16384"))
DPI = int(os.getenv("VISION_DPI", "150"))
MAX_PAGES = int(os.getenv("VISION_MAX_PAGES", "2"))
TIMEOUT = int(os.getenv("VISION_TIMEOUT_S", "900"))

COMMON_RULES = """
ОБЩИЕ ПРАВИЛА (обязательны):
- Переписывай значения ровно так, как они напечатаны. Ничего не придумывай; если поля нет — пустая строка или null.
- ИНН — 10 или 12 цифр, КПП — 9 знаков. Не путай ИНН продавца и покупателя.
- Ставку НДС пиши как напечатано: «22%», «10%», «0%» или «без НДС». «Без НДС» и «0%» — разные вещи, не заменяй одно другим.
  Слова «без акциза» относятся к акцизу, а не к НДС.
- Номер договора ищи в строке «Основание передачи», в наименовании услуги («согласно Договору № …») или в шапке.
  Номер платёжного документа (строка «К платёжно-расчётному документу») — это НЕ номер договора.
- Числа пиши без пробелов, с точкой: 1373938.95.
- ИНН/КПП сторон стоят в строках «ИНН/КПП продавца» и «ИНН/КПП покупателя» — обязательно перепиши их.
- Количество переписывай целиком (все цифры). Проверь себя: количество × цена ≈ стоимость строки.
"""

TYPE_SCHEMA = {
    "type": "object",
    "properties": {
        "doc_type": {"type": "string", "enum": ["УПД", "Счет-фактура", "ТОРГ-12", "Акт", "Договор", "Доверенность", "Другое"]},
        "title": {"type": "string"},
    },
    "required": ["doc_type", "title"],
}

ITEM = {"type": "object", "properties": {
    "row_num": {"type": "string"}, "name": {"type": "string"}, "unit": {"type": "string"},
    "quantity": {"type": ["number", "null"]}, "price": {"type": ["number", "null"]},
    "amount_no_vat": {"type": ["number", "null"]}, "vat_rate": {"type": "string"},
    "vat_amount": {"type": ["number", "null"]}, "total_amount": {"type": ["number", "null"]}},
    "required": ["name", "quantity", "price", "amount_no_vat", "vat_rate", "vat_amount", "total_amount"]}


def render(path: str, dpi: int = DPI, max_pages: int = MAX_PAGES) -> List[str]:
    doc = pdfium.PdfDocument(path)
    out = []
    try:
        for i in range(min(len(doc), max_pages)):
            img = doc[i].render(scale=dpi / 72).to_pil().convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            out.append(base64.b64encode(buf.getvalue()).decode())
    finally:
        doc.close()
    return out


def _ollama(prompt: str, images: List[str], schema: dict, model: str) -> dict:
    body = {"model": model, "stream": False, "format": schema,
            "options": {"temperature": 0, "num_ctx": NUM_CTX},
            "messages": [{"role": "user", "content": prompt, "images": images}]}
    req = urllib.request.Request(OLLAMA_URL.rstrip("/") + "/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        resp = json.loads(r.read().decode())
    content = (resp.get("message") or {}).get("content", "")
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", content, re.S)
        return json.loads(m.group(0)) if m else {}


def _definition(def_id: str):
    man = json.load(open(os.path.join(DEF_DIR, def_id, "manifest.json"), encoding="utf-8"))
    prompt = open(os.path.join(DEF_DIR, def_id, "prompt.md"), encoding="utf-8").read()
    mod = importlib.import_module(f"definitions.{def_id}.schema")
    return prompt, getattr(mod, man["schema_class"])


def _simplify(node):
    """Для структурного вывода Ollama: Optional[str] (anyOf string|null) -> string, все поля объектов обязательны.
    Иначе модель пропускает поля со значением по умолчанию (так терялись ИНН/КПП сторон)."""
    if isinstance(node, dict):
        if "anyOf" in node:
            alts = [a for a in node["anyOf"] if a.get("type") != "null"]
            if len(alts) == 1:
                rest = {k: v for k, v in node.items() if k != "anyOf"}
                node = {**alts[0], **rest}
        node = {k: _simplify(v) for k, v in node.items()}
        if node.get("type") == "object" and isinstance(node.get("properties"), dict):
            node["required"] = list(node["properties"].keys())
        return node
    if isinstance(node, list):
        return [_simplify(x) for x in node]
    return node


def _schema_for(def_id: str, model_cls) -> dict:
    sch = _simplify(model_cls.model_json_schema())
    props = sch.setdefault("properties", {})
    if def_id == "invoices_upd":
        props["payment_docs"] = {"type": "string", "description": "К платёжно-расчётному документу: № и дата"}
        props["doc_kind"] = {"type": "string", "enum": ["УПД", "Счет-фактура", "ТОРГ-12"]}
    if def_id == "acceptance_certificates":
        props["items"] = {"type": "array", "items": ITEM}
    return _simplify(sch)


def _validate(model_cls, data: dict):
    """Проверка схемой определения; ошибки не роняют чтение, а возвращаются списком."""
    from pydantic import ValidationError
    try:
        model_cls.model_validate(data)
        return []
    except ValidationError as e:
        return [f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()][:10]


def _lines(items) -> list:
    out = []
    for i, it in enumerate(items or [], 1):
        rate = norm_rate(it.get("vat_rate", ""))
        swo, vs, sw = num(it.get("amount_no_vat")), num(it.get("vat_amount")), num(it.get("total_amount"))
        if rate == "Без НДС":
            vs = 0.0
            sw = sw if sw is not None else swo
        rn = clean(it.get("row_num", ""))
        out.append({"line_no": int(rn) if rn.isdigit() else i, "name": clean(it.get("name", "")),
                    "unit": clean(it.get("unit", "")), "qty": money(num(it.get("quantity"))),
                    "price": money(num(it.get("price"))), "sum_without_vat": money(swo), "vat_rate": rate,
                    "vat_sum": money(vs), "sum_with_vat": money(sw)})
    return out


def to_card(def_id: str, doc_type: str, d: dict) -> dict:
    c = dict(EMPTY, lines=[])
    c["doc_type"], c["doc_type_id"] = doc_type, def_id
    c["doc_number"] = clean(d.get("doc_number", ""))
    c["doc_date"] = norm_date(d.get("doc_date", "") or d.get("issue_date", "")) or clean(d.get("doc_date", ""))
    if def_id in ("invoices_upd", "invoices_sf"):
        st = re.sub(r"\D", "", str(d.get("status", "")))
        kind = d.get("doc_kind") or doc_type
        # статус 1/2 печатается только в УПД; модель иногда пишет «Счет-фактура» по первой строке заголовка
        c["doc_type"] = "УПД" if st in ("1", "2") and kind != "ТОРГ-12" else kind
        c["upd_status"] = st if c["doc_type"] == "УПД" and st in ("1", "2") else ""
        s, b = d.get("seller") or {}, d.get("buyer") or {}
        c["basis"] = clean(d.get("contract_base", ""))
        pd = clean(d.get("payment_docs", ""))
        # модель путает «К платёжно-расчётному документу» с самим документом — свой номер платёжкой не считаем
        if c["doc_number"] and c["doc_number"] in pd or re.search(r"(?i)универсальн|передаточн|счет-фактур|счёт-фактур", pd):
            pd = ""
        c["payment_docs"] = payment_docs_from(pd) or pd
        c["lines"] = _lines(d.get("items"))
        if c["doc_type"] == "Счет-фактура":
            for k in ("correction_number", "correction_date", "shipping_doc", "currency"):
                c[k] = clean(d.get(k, ""))
            c["shipper"] = clean((d.get("shipper") or {}).get("name", "")) if isinstance(d.get("shipper"), dict) else ""
            c["consignee"] = clean((d.get("consignee") or {}).get("name", "")) if isinstance(d.get("consignee"), dict) else ""
        f = d.get("finances") or {}
        c["total_without_vat"], c["total_vat"], c["total_with_vat"] = (money(num(f.get(k))) for k in ("total_rub_no_vat", "total_vat_rub", "total_rub"))
    elif def_id == "acceptance_certificates":
        s, b = d.get("contractor") or {}, d.get("customer") or {}
        c["contract_number"], c["contract_date"] = clean(d.get("contract_number", "")), norm_date(d.get("contract_date", ""))
        c["lines"] = _lines(d.get("items"))
        if c["doc_type"] == "Счет-фактура":
            for k in ("correction_number", "correction_date", "shipping_doc", "currency"):
                c[k] = clean(d.get(k, ""))
            c["shipper"] = clean((d.get("shipper") or {}).get("name", "")) if isinstance(d.get("shipper"), dict) else ""
            c["consignee"] = clean((d.get("consignee") or {}).get("name", "")) if isinstance(d.get("consignee"), dict) else ""
        f = d.get("finances") or {}
        c["total_without_vat"], c["total_vat"], c["total_with_vat"] = (money(num(f.get(k))) for k in ("amount_no_vat_rub", "vat_amount_rub", "total_rub"))
        if norm_rate(f.get("vat_rate", "")) == "Без НДС":
            c["vat_mode"] = "без НДС"
    elif def_id == "commercial_contracts":
        s, b = d.get("party_two") or {}, d.get("party_one") or {}
        c["subject"] = clean(d.get("claim_subject", ""))
        f = d.get("finances") or {}
        c["total_with_vat"] = money(num(f.get("total_rub")))
    else:  # powers_of_attorney
        s, b = d.get("principal") or {}, {}
        c["valid_until"] = clean(d.get("valid_until", ""))
        c["agent_name"] = clean((d.get("agent") or {}).get("full_name", ""))
    c["seller_name"], c["seller_inn"], c["seller_kpp"] = clean(s.get("name", "")), re.sub(r"\D", "", str(s.get("inn") or "")), clean(s.get("kpp") or "")
    c["buyer_name"], c["buyer_inn"], c["buyer_kpp"] = clean(b.get("name", "")), re.sub(r"\D", "", str(b.get("inn") or "")), clean(b.get("kpp") or "")
    if not c["contract_number"] and def_id in ("invoices_upd", "invoices_sf", "acceptance_certificates"):
        for sc in [c["basis"]] + [l["name"] for l in c["lines"]]:
            n, dt = contract_from(sc)
            if n:
                c["contract_number"], c["contract_date"] = n, dt
                break
    if c["lines"]:
        c["vat_mode"] = vat_mode_of(c["lines"], c["total_vat"])
        c["vat_rate"] = doc_rate(c["lines"])
    return c


def read_vision(path: str, model: Optional[str] = None, text_pages=None) -> dict:
    model = model or MODEL
    t0 = time.time()
    warnings: List[str] = []
    try:
        imgs = render(path)
        small = render(path, dpi=90, max_pages=1)
        t = _ollama("Определи вид документа на картинке (российский бухгалтерский документ). "
                    "УПД — универсальный передаточный документ со статусом 1 или 2. Ответь JSON.", small, TYPE_SCHEMA, model)
        doc_type = t.get("doc_type", "Другое")
        def_id = TYPE_DEF.get(doc_type, "")
        if not def_id:
            card = finish(dict(EMPTY, lines=[]), [f"по картинке документ определён как «{doc_type}» ({t.get('title', '')}) — не поддерживается"])
            card.update(source="vision", vision_model=model, vision_s=round(time.time() - t0, 1))
            return card
        prompt, cls = _definition(def_id)
        data = _ollama(prompt + "\n" + COMMON_RULES, imgs, _schema_for(def_id, cls), model)
        card = to_card(def_id, doc_type, data)
        errs = _validate(cls, data)
        if errs:
            warnings.append("схема определения: " + "; ".join(errs))
        warnings.append("документ прочитан по картинке моделью — проверьте реквизиты по оригиналу")
        card = finish(card, warnings)
        card.update(source="vision", vision_model=model, vision_s=round(time.time() - t0, 1), vision_raw=data)
        return card
    except Exception as e:  # сеть / Ollama / модель
        card = finish(dict(EMPTY, lines=[]), [f"чтение по картинке не удалось: {type(e).__name__}: {e}"])
        card.update(source="vision", vision_model=model, vision_error=str(e))
        return card
