# -*- coding: utf-8 -*-
"""Слияние двух прочтений скана по полям (MERGE_DESIGN): способ 1 = OCR + графы, способ 2 = qwen2.5vl.
Совпали -> берём; разошлись -> берём то, что проходит проверку; иначе пусто + «неразборчиво на скане».
Результат: card + card["merge"] = [{field, method1, method2, final, reason}] -> Excel «Способ 1 / Способ 2 / Итог / Почему»."""
import os
import re
from typing import List, Optional

HEAD = ["doc_type", "upd_status", "doc_number", "doc_date", "seller_inn", "seller_name", "seller_kpp", "buyer_inn", "buyer_name",
        "buyer_kpp", "contract_number", "contract_date", "payment_docs", "total_without_vat", "total_vat",
        "total_with_vat"]
LINE = ["name", "qty", "price", "sum_without_vat", "vat_rate", "vat_sum", "sum_with_vat"]
UNCLEAR = "неразборчиво на скане"


def inn_ok(s) -> bool:
    d = [int(c) for c in str(s or "")] if str(s or "").isdigit() else []
    f = lambda w: sum(a * b for a, b in zip(w, d)) % 11 % 10
    if len(d) == 10:
        return f([2, 4, 10, 3, 5, 9, 4, 6, 8]) == d[9]
    if len(d) == 12:
        return f([7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) == d[10] and f([3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) == d[11]
    return False


def _same(a, b) -> bool:
    if a in ("", None) or b in ("", None):
        return False
    try:
        return abs(float(a) - float(b)) < 0.005
    except (TypeError, ValueError):
        n = lambda x: re.sub(r"[\s\"«»'.,]", "", str(x)).lower().translate(str.maketrans("abcekmhoptxy", "авсекмнортху"))
        return n(a) == n(b)


def _valid(field: str, v, card: dict, our_inn: str) -> Optional[bool]:
    """True/False — проверка есть; None — для поля проверки нет."""
    if v in ("", None):
        return False
    if field.endswith("_inn"):
        if not inn_ok(v):
            return False
        if our_inn and field == "buyer_inn":
            return str(v) == our_inn
        if our_inn and field == "seller_inn":
            return str(v) != our_inn
        return True
    if field.endswith("_kpp"):
        return bool(re.fullmatch(r"\d{9}", str(v)))
    if field == "doc_date" or field == "contract_date":
        return bool(re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", str(v)))
    if field == "total_with_vat":
        ls = card.get("lines") or []
        if ls:
            return abs(sum(float(l.get("sum_with_vat") or 0) for l in ls) - float(v)) < 0.05
    return None


def _line_ok(l: dict) -> Optional[bool]:
    try:
        return abs(float(l["qty"]) * float(l["price"]) - float(l["sum_without_vat"])) < 0.05
    except (TypeError, ValueError, KeyError):
        return None


def _pick(field, a, b, ca, cb, our):
    if _same(a, b) or (a == b and a not in ("", None)):
        return a, "совпали"
    if a in ("", None) and b in ("", None):
        return "", "нет ни в одном способе"
    va, vb = _valid(field, a, ca, our), _valid(field, b, cb, our)
    if va and not vb:
        return a, "способ 1 проходит проверку" + ("" if b not in ("", None) else ", способ 2 пусто")
    if vb and not va:
        return b, "способ 2 проходит проверку" + ("" if a not in ("", None) else ", способ 1 пусто")
    if va is None and vb is None:
        if a in ("", None):
            return b, "есть только в способе 2 (проверки нет) — проверьте"
        if b in ("", None):
            return a, "есть только в способе 1 (проверки нет) — проверьте"
    return "", f"{UNCLEAR}: способы разошлись, проверка не решает"


def merge(c1: dict, c2: Optional[dict], our_inn: str = None) -> dict:
    our = our_inn if our_inn is not None else os.getenv("DOCREADER_OUR_INN", "")
    c2 = c2 or {}
    out = dict(c1)
    rows: List[dict] = []
    won = {1: 0, 2: 0}
    party_src = {}
    for f in HEAD:
        role = f.split("_")[0] if f.split("_")[0] in ("seller", "buyer") else ""
        if c2 and role and f != f"{role}_inn" and role in party_src:
            # наименование и КПП стороны — из того же способа, чей ИНН выбран (иначе стороны перемешаются)
            src = party_src[role]
            v = (c1 if src == 1 else c2).get(f, "")
            why = "совпали" if _same(c1.get(f, ""), c2.get(f, "")) else f"сторона взята из способа {src} (по ИНН)"
        else:
            v, why = _pick(f, c1.get(f, ""), c2.get(f, ""), c1, c2, our) if c2 else (c1.get(f, ""), "только способ 1")
        if c2 and role and f == f"{role}_inn":
            party_src[role] = 2 if (why.startswith("способ 2") or why.startswith("есть только в способе 2")) else 1
        if why.startswith("способ 1 проходит"):
            won[1] += 1
        elif why.startswith("способ 2 проходит"):
            won[2] += 1
        out[f] = v
        rows.append({"field": f, "method1": c1.get(f, ""), "method2": c2.get(f, "") if c2 else "", "final": v, "reason": why})
    trust2 = won[2] >= won[1]
    l1, l2 = c1.get("lines") or [], c2.get("lines") or []
    lines = []
    for i in range(max(len(l1), len(l2))):
        a = l1[i] if i < len(l1) else {}
        b = l2[i] if i < len(l2) else {}
        oka, okb = _line_ok(a) if a else None, _line_ok(b) if b else None
        ln = {"line_no": i + 1}
        for f in LINE:
            x, y = a.get(f, ""), b.get(f, "")
            if f == "name":
                if x and y and _same(x, y):
                    v, why = x, "совпали"
                elif not c2 or not y:
                    v, why = x, "только способ 1" if not c2 else "способ 2 пусто"
                elif not x:
                    v, why = y, "способ 1 пусто"
                elif okb and not oka:
                    v, why = y, "строка сходится только у способа 2"
                elif oka and not okb:
                    v, why = x, "строка сходится только у способа 1 — наименование по OCR, проверьте"
                elif trust2:
                    v, why = y, "наименование — способ 2 (картинка), OCR мелкого шрифта ненадёжен"
                else:
                    v, why = x, "способ 2 проиграл проверки шапки — наименование по OCR, проверьте"
            elif not c2:
                v, why = x, "только способ 1"
            elif f == "vat_rate" and {str(x), str(y)} == {"Без НДС", "0%"} and not float(a.get("vat_sum") or 0) and not float(b.get("vat_sum") or 0):
                v, why = "Без НДС", "НДС 0 в обоих способах; «0%» модели при нулевом НДС обычно означает «без НДС» — проверьте"
            elif _same(x, y):
                v, why = x, "совпали"
            elif oka and not okb:
                v, why = x, "кол-во × цена сходится только у способа 1"
            elif okb and not oka:
                v, why = y, "кол-во × цена сходится только у способа 2"
            elif x in ("", None) or y in ("", None):
                v, why = (x or y), "есть только в одном способе — проверьте"
            else:
                v, why = "", f"{UNCLEAR}: строки разошлись"
            ln[f] = v
            rows.append({"field": f"строка {i + 1}: {f}", "method1": x, "method2": y, "final": v, "reason": why})
        lines.append(ln)
    out["lines"] = lines
    out["merge"] = rows
    out["merge_note"] = "" if c2 else "второй способ (qwen) не запускался — итог = способ 1"
    return out


def write_xlsx(card: dict, path: str) -> str:
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    ws = wb.active
    ws.title = "Реквизиты"
    ws.append(["Поле", "Способ 1", "Способ 2", "Итог", "Почему"])
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in card.get("merge", []):
        ws.append([r["field"], str(r["method1"]), str(r["method2"]), str(r["final"]), r["reason"]])
    for col, w in zip("ABCDE", (28, 40, 40, 40, 50)):
        ws.column_dimensions[col].width = w
    wb.save(path)
    return path
