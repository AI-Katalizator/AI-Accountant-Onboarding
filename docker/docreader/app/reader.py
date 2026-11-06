# -*- coding: utf-8 -*-
"""Чтение документа: текстовый слой (pdfplumber) или картинка -> qwen2.5vl (pypdfium2 + Ollama)."""
import re
import time
from typing import Dict, List, Optional

import pdfplumber

from . import checks as checks_mod
from . import header as H
from .classify import TYPE_DEF, classify
from .tables import colnum_table, label_table
from .util import clean, join_wrapped, vocab_of, money, norm_rate, num

VERSION = "0.2.0-dev"


def _outcomes():
    import json, os
    from .classify import DEF_DIR, DEF_TYPE
    out = {}
    for d in DEF_TYPE:
        try:
            out[d] = json.load(open(os.path.join(DEF_DIR, d, "manifest.json"), encoding="utf-8")).get("outcome_note", "")
        except OSError:
            out[d] = ""
    return out


OUTCOME = _outcomes()
NUMRX = r"(\d{1,3}(?:[ \u00a0]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"


def text_of(pdf) -> List[str]:
    return [(p.extract_text() or "") for p in pdf.pages]


def has_text_layer(pages: List[str]) -> bool:
    letters = sum(len(re.findall(r"[А-Яа-яЁё]", t)) for t in pages)
    return letters >= 80


# ------------------------------------------------------------------ строки таблицы
def lines_from_colnum(tab: dict, vocab=None) -> List[dict]:
    out = []
    from .tables import OFFICIAL
    m = dict(OFFICIAL[tab["kind"]])
    m.update(tab.get("fieldmap") or {})
    for i, r in enumerate(tab["rows"], 1):
        g = lambda k: clean(r.get(m.get(k, "-"), ""))
        rate = norm_rate(g("vat_rate"))
        vs_raw = g("vat_sum")
        if not rate and re.search(r"(?i)без\s*ндс", vs_raw):
            rate = "Без НДС"
        if rate == "" and re.fullmatch(r"(--|-|—|x|х|X|Х)?", g("vat_rate")):
            rate = "Без НДС" if not num(vs_raw) else ""
        swo, sw = num(g("sum_without_vat")), num(g("sum_with_vat"))
        vs = num(vs_raw)
        if rate == "Без НДС":
            vs = 0.0
            if sw is None:
                sw = swo
        if swo is None and sw is not None and vs is not None:
            swo = round(sw - vs, 2)  # графа 5 пустая (бывает в Диадоке): с налогом − налог
        ln = g("line_no").split(" ")[0]
        out.append({
            "line_no": int(ln) if ln.isdigit() else i,
            "name": join_wrapped(r.get(m["name"], ""), vocab),
            "unit": g("unit") or g("unit_code"),
            "qty": money(num(g("qty"))) if num(g("qty")) is not None else "",
            "price": money(num(g("price"))),
            "sum_without_vat": money(swo),
            "vat_rate": rate,
            "vat_sum": money(vs),
            "sum_with_vat": money(sw),
        })
    return out


def totals_from_colnum(tab: dict) -> Dict:
    from .tables import OFFICIAL
    t = tab.get("totals") or {}
    m = dict(OFFICIAL[tab["kind"]])
    m.update(tab.get("fieldmap") or {})
    wo, v, w = t.get(m["sum_without_vat"]), t.get(m["vat_sum"]), t.get(m["sum_with_vat"])
    return {"total_without_vat": num(wo), "total_vat": num(v), "total_with_vat": num(w),
            "total_vat_raw": clean(v or "")}


def lines_from_label(tab: dict, text: str):
    """Акт: строки из свободной таблицы + итоги из текста под таблицей."""
    tot = act_totals(text)
    out = []
    for i, r in enumerate(tab["rows"], 1):
        s = num(r.get("sum")) if r.get("sum") else None
        swo = num(r.get("sum_without_vat"))
        sw = num(r.get("sum_with_vat"))
        vs = num(r.get("vat_sum"))
        rate = norm_rate(r.get("vat_rate", "")) or tot["rate"]
        if s is not None and swo is None and sw is None:
            if tot["mode"] == "без НДС":
                swo = sw = s
                vs = 0.0
            elif tot["mode"] == "в том числе":
                sw = s
            else:  # НДС сверху или неизвестно
                swo = s
        if rate == "Без НДС":
            vs = 0.0
            sw = sw if sw is not None else swo
        if sw is None and swo is not None and vs is not None:
            sw = swo + vs
        if sw is None and swo is not None and re.fullmatch(r"\d+(\.\d+)?%", rate or "") and len(tab["rows"]) >= 1:
            vs = round(swo * float(rate[:-1]) / 100, 2)
            sw = swo + vs
        if swo is None and sw is not None and re.fullmatch(r"\d+(\.\d+)?%", rate or ""):
            vs = round(sw * float(rate[:-1]) / (100 + float(rate[:-1])), 2)
            swo = sw - vs
        ln = clean(r.get("line_no", ""))
        out.append({"line_no": int(ln) if ln.isdigit() else i, "name": clean(r.get("name", "")),
                    "unit": clean(r.get("unit", "")), "qty": money(num(r.get("qty"))),
                    "price": money(num(r.get("price"))), "sum_without_vat": money(swo), "vat_rate": rate,
                    "vat_sum": money(vs), "sum_with_vat": money(sw)})
    return out, tot


def act_totals(text: str) -> Dict:
    t = re.sub(r"[ \t]+", " ", text)
    res = {"mode": "", "rate": "", "total_without_vat": None, "total_vat": None, "total_with_vat": None}
    # «Итого без НДС: 100,00» / «Сумма без НДС» — это подпись суммы, а не признак «без НДС»
    wo = re.search(r"(?im)(?:итого|всего|сумма)\s+без\s+ндс[ \t]*:?[ \t]*" + NUMRX, t)
    vat_pos = re.search(r"(?im)^\s*(?:итого\s+|всего\s+)?(?:сумма\s+)?ндс[ \t]*(?:\(?[ \t]*(\d{1,2})[ \t]*%[ \t]*\)?)?[ \t]*:?[ \t]*" + NUMRX, t)
    t_nolabels = re.sub(r"(?i)(?:итого|всего|сумма)\s+без\s+ндс", " ", t)
    t_nolabels = re.sub(r"(?im)^.*наименован.*$", " ", t_nolabels)  # шапка таблицы
    if vat_pos and num(vat_pos.group(2)) and num(vat_pos.group(2)) > 0:
        pass
    elif re.search(r"(?i)без\s+(налога\s*\(?ндс\)?|ндс)|ндс\s+не\s+облагается|не\s+облагается\s+ндс|ндс\s*:?\s*не\s+предусмотрен", t_nolabels):
        res["mode"], res["rate"] = "без НДС", "Без НДС"
    m = re.search(r"(?i)в\s+том\s+числе\s+ндс\s*(?:\(?\s*(\d{1,2})\s*%\s*\)?)?\s*:?\s*" + NUMRX, t)
    if m and not res["mode"]:
        res["mode"] = "в том числе"
        res["rate"] = (m.group(1) + "%") if m.group(1) else ""
        res["total_vat"] = num(m.group(2))
    m2 = vat_pos
    if m2 and not res["mode"]:
        res["mode"] = "сверху"
        res["rate"] = (m2.group(1) + "%") if m2.group(1) else ""
        res["total_vat"] = num(m2.group(2))
    it = re.search(r"(?im)^\s*итого\s*:?\s*" + NUMRX, t)
    vs = re.search(r"(?i)всего[ \t]*(?:к[ \t]+оплате|по[ \t]+акту|с[ \t]+(?:учетом[ \t]+)?ндс|\(с[ \t]+учетом[ \t]+ндс\))?[ \t]*:?[ \t]*" + NUMRX + r"(?![\d.,]*[ \t]+[А-Яа-я]{4,})", t)
    na = re.search(r"(?i)на\s+сумму\s*:?\s*" + NUMRX, t)
    itv = num(it.group(1)) if it else None
    allv = num(vs.group(1)) if vs else (num(na.group(1)) if na else None)
    if res["mode"] == "без НДС":
        res["total_vat"] = 0.0
        res["total_with_vat"] = allv if allv is not None else itv
        res["total_without_vat"] = res["total_with_vat"]
    elif res["mode"] == "в том числе":
        res["total_with_vat"] = itv if itv is not None else allv
        if res["total_with_vat"] is not None and res["total_vat"] is not None:
            res["total_without_vat"] = round(res["total_with_vat"] - res["total_vat"], 2)
    elif res["mode"] == "сверху":
        res["total_without_vat"] = num(wo.group(1)) if wo else itv
        if itv is None and wo:
            itv = res["total_without_vat"]
        res["total_with_vat"] = allv if allv is not None and itv is not None and allv != itv else (
            round(itv + res["total_vat"], 2) if itv is not None and res["total_vat"] is not None else allv)
    else:
        res["total_with_vat"] = allv if allv is not None else itv
    return res


def vat_mode_of(lines, total_vat) -> str:
    rates = [l["vat_rate"] for l in lines if l.get("vat_rate")]
    if rates and all(r == "Без НДС" for r in rates):
        return "без НДС"
    if any(r.endswith("%") or "/" in r for r in rates):
        return "с НДС"
    if total_vat not in (None, ""):
        return "с НДС" if float(total_vat) > 0 else "неизвестно"
    return "неизвестно"


def doc_rate(lines) -> str:
    rates = sorted({l["vat_rate"] for l in lines if l.get("vat_rate")})
    return rates[0] if len(rates) == 1 else ("смешанная: " + ", ".join(rates) if rates else "")


# ------------------------------------------------------------------ карточка
EMPTY = {
    "doc_type": "", "doc_type_id": "", "upd_status": "", "doc_number": "", "doc_date": "",
    "seller_name": "", "seller_inn": "", "seller_kpp": "", "buyer_name": "", "buyer_inn": "", "buyer_kpp": "",
    "contract_number": "", "contract_date": "", "payment_docs": "", "basis": "",
    "total_without_vat": "", "total_vat": "", "total_with_vat": "", "vat_mode": "неизвестно", "vat_rate": "",
    "lines": [], "lines_sum": 0, "check_lines_sum": "нет строк",
}


def finish(card: dict, warnings: List[str]) -> dict:
    lines = card.get("lines") or []
    s = round(sum(float(l.get("sum_with_vat") or 0) for l in lines), 2)
    card["lines_sum"] = s
    tw = card.get("total_with_vat")
    card["check_lines_sum"] = "нет строк" if not lines else ("нет итога" if tw in ("", None) else ("да" if abs(s - float(tw)) < 0.05 else "нет"))
    card["checks"] = checks_mod.run(card)
    card["checks_ok"] = not any(c["status"] == "error" for c in card["checks"])
    card["warnings"] = warnings + [c["message"] for c in card["checks"] if c["status"] in ("error", "warning")]
    card["warnings_ocr"] = list(card["warnings"])  # то же поле, что в v003
    return card


def read_text_layer(pdf, pages: List[str]) -> dict:
    text = "\n".join(pages)
    warnings: List[str] = []
    doc_type, def_id, reasons = classify(text)
    card = dict(EMPTY, lines=[])
    card.update(doc_type=doc_type, doc_type_id=def_id, classify_reasons=reasons)
    if doc_type in ("УПД", "Счет-фактура"):
        hd = H.upd_header(text)
        if doc_type == "Счет-фактура":
            card.update(H.sf_extra(text))
            card["outcome_note"] = OUTCOME.get(def_id, "")
    elif doc_type == "ТОРГ-12":
        hd = H.torg12_header(text)
    elif doc_type == "Акт":
        hd = H.act_header(text)
    elif doc_type == "Договор":
        hd = H.contract_doc_header(text)
        if not hd.get("seller_inn") and not hd.get("buyer_inn"):
            hd.update(seller_inn=hd.get("party2_inn", ""), buyer_inn=hd.get("party1_inn", ""),
                      seller_kpp=hd.get("party2_kpp", ""), buyer_kpp=hd.get("party1_kpp", ""))
            warnings.append("договор: роли сторон не найдены, стороны взяты по порядку ИНН в тексте — проверьте")
        card["subject"] = hd.get("subject", "")
    elif doc_type == "Доверенность":
        hd = H.poa_header(text)
        card["valid_until"] = hd.get("valid_until", "")
        card["principal_inn"] = hd.get("principal_inn", "")
    else:
        hd = {}
    for k in ("doc_number", "doc_date", "upd_status", "seller_name", "seller_inn", "seller_kpp",
              "buyer_name", "buyer_inn", "buyer_kpp", "payment_docs", "basis"):
        if hd.get(k):
            card[k] = hd[k]
    tab = None
    if doc_type in ("УПД", "Счет-фактура", "ТОРГ-12"):
        tab = colnum_table(pdf)
        if tab:
            card["lines"] = lines_from_colnum(tab, vocab_of(text))
            tot = totals_from_colnum(tab)
            for k in ("total_without_vat", "total_vat", "total_with_vat"):
                card[k] = money(tot[k])
            if card["total_vat"] == "" and re.search(r"(?i)без\s*ндс|^[xх—-]$|^$", tot.get("total_vat_raw", "")) \
                    and card["lines"] and all(l["vat_rate"] in ("Без НДС", "0%") for l in card["lines"]):
                card["total_vat"] = 0.0
            if card["total_without_vat"] == "" and card["total_vat"] == 0.0:
                card["total_without_vat"] = card["total_with_vat"]
        else:
            warnings.append("не найдена строка номеров граф («А 1 1а …») — строки таблицы не прочитаны")
    elif doc_type == "Акт":
        tab = label_table(pdf)
        tot = act_totals(text)
        if tab:
            card["lines"], tot = lines_from_label(tab, text)
        else:
            warnings.append("в акте не найдена таблица работ/услуг")
        for k in ("total_without_vat", "total_vat", "total_with_vat"):
            card[k] = money(tot[k])
        if tot["mode"] == "без НДС":
            card["vat_mode"] = "без НДС"
    # договор: основание -> строки таблицы -> весь текст (без строки платёжек)
    scopes = [card.get("basis", "")] + [l["name"] for l in card["lines"]] + \
             [text.replace(hd.get("payment_docs_raw", "") or "\u0000", " ")]
    if doc_type not in ("Договор", "Доверенность"):
        for sc in scopes:
            n, d = H.contract_from(sc)
            if n:
                card["contract_number"], card["contract_date"] = n, d
                break
    pays = H.payment_numbers(card.get("payment_docs", ""))
    if card["contract_number"] and card["contract_number"] in pays:
        found_elsewhere = any(H.contract_from(sc)[0] == card["contract_number"] for sc in scopes[:-1])
        if found_elsewhere:
            warnings.append(f"в строке «К платёжно-расчётному документу» указан договор № {card['contract_number']}, "
                            "а не платёжка — платёжные документы оставлены пустыми")
            card["payment_docs_original"] = card["payment_docs"]
            card["payment_docs"] = ""
    if card["lines"]:
        card["vat_mode"] = vat_mode_of(card["lines"], card["total_vat"])
        card["vat_rate"] = doc_rate(card["lines"])
    elif card["vat_mode"] == "неизвестно" and card["total_vat"] not in ("", None):
        card["vat_mode"] = "с НДС" if float(card["total_vat"]) > 0 else "неизвестно"
    if tab:
        card["table"] = {k: tab[k] for k in ("kind", "columns") if k in tab}
        card["table"]["grid"] = tab.get("grid")
    card["doc_text"] = text
    return finish(card, warnings)


def read_scan(path: str, second: str = "none", model: Optional[str] = None, our_inn: Optional[str] = None) -> dict:
    """Скан: способ 1 = OCR (ocrmypdf) + чтение графами; способ 2 (по флагу second="qwen") = qwen2.5vl; слияние по полям."""
    from . import ocr as O, scan as S, merge as M
    o = O.ocr_pdf(path)
    warnings: List[str] = []
    if not o["ok"]:
        c1 = finish(dict(EMPTY, lines=[]), [f"OCR не выполнен: {o['error']}"])
        c1["source"] = "none"
    else:
        with pdfplumber.open(o["pdf"]) as pdf:
            pages = [S.normalize(t) for t in text_of(pdf)]
            c1 = read_text_layer(pdf, pages)
            text = "\n".join(S.normalize(p.extract_text(layout=True) or "") for p in pdf.pages)
        warnings = [w for w in c1.get("warnings", []) if w not in [c["message"] for c in c1.get("checks", [])]]
        warnings = [w for w in warnings if "строка номеров граф" not in w and "строки таблицы не найдены" not in w]
        S.apply(c1, text, warnings)
        c1 = finish(c1, warnings)
        c1["source"] = "ocr"
    c1["ocr"] = {k: o[k] for k in ("ok", "elapsed_s", "settings", "error")}
    c1["ocr"]["pdf"] = o["pdf"]
    c2 = None
    if second == "qwen":
        from . import vision as V
        try:
            c2 = V.read_vision(path, model=model)
        except Exception as e:  # noqa: BLE001
            c1["warnings"].append(f"второй способ (qwen) не сработал: {e!r}")
    card = M.merge(c1, c2, our_inn=our_inn)
    if c2 is not None:
        card = finish(card, list(c1["warnings"]) + [f"qwen: {w}" for w in c2.get("warnings", [])])
        card["source"] = "ocr+vision"
    card["method1"] = {k: c1.get(k) for k in M.HEAD + ["lines"]}
    if c2 is not None:
        card["method2"] = {k: c2.get(k) for k in M.HEAD + ["lines"]}
    return card


def read(path: str, vision: str = "auto", model: Optional[str] = None, scan: Optional[str] = None,
         our_inn: Optional[str] = None) -> dict:
    """vision: auto|never|always (как раньше). scan: ocr|ocr+qwen|qwen (по умолчанию из DOCREADER_SCAN_MODE, иначе ocr).
    vision="never" не отключает OCR: OCR — локальный шаг без модели."""
    import os
    t0 = time.time()
    scan = scan or os.getenv("DOCREADER_SCAN_MODE", "ocr")
    with pdfplumber.open(path) as pdf:
        pages = text_of(pdf)
        text_ok = has_text_layer(pages)
        card = None
        if text_ok and vision != "always":
            card = read_text_layer(pdf, pages)
            card["source"] = "text_layer"
        n_pages = len(pdf.pages)
    if not text_ok and vision != "always" and scan in ("ocr", "ocr+qwen"):
        card = read_scan(path, second="qwen" if (scan == "ocr+qwen" and vision != "never") else "none", model=model,
                         our_inn=our_inn)
        card["pages"] = n_pages
        card["elapsed_s"] = round(time.time() - t0, 2)
        card["reader_version"] = VERSION
        return card
    need_vision = vision == "always" or (not text_ok and vision != "never") or (
        vision == "auto" and card is not None and not card["doc_type"])
    if need_vision:
        from . import vision as V
        vcard = V.read_vision(path, model=model, text_pages=pages if text_ok else None)
        if card is not None and not card["doc_type"]:
            vcard["warnings"].insert(0, "текстовый слой есть, но тип документа по нему не определён — прочитано по картинке")
        card = vcard
    elif card is None:
        card = finish(dict(EMPTY, lines=[]), ["в PDF нет текстового слоя, а чтение по картинке выключено"])
        card["source"] = "none"
    card["pages"] = n_pages
    card["elapsed_s"] = round(time.time() - t0, 2)
    card["reader_version"] = VERSION
    return card
