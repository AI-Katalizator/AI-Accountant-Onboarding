# -*- coding: utf-8 -*-
"""Чтение скана после OCR (способ 1): нормализация OCR-текста + шапка regex + графы (если ряд номеров граф распознан)
+ запасной разбор строк: по заголовку «Наименование…» / цепочке «ед. → кол-во → цена → сумма», строка ищется по трём
числам и проверке кол-во × цена = сумма, без опоры на слово единицы измерения."""
import re
from typing import Dict, List, Optional, Tuple

from . import header as H
from .util import clean, money

LAT = str.maketrans("ABCEHKMOPTXaceopxy", "АВСЕНКМОРТХасеорху")
MONTHS = {m: i + 1 for i, m in enumerate("января февраля марта апреля мая июня июля августа сентября октября ноября декабря".split())}
OUR_UNITS = r"(?:шт|чел|усл\.?\s*ед|ед|час|мес|кг|упак|компл|м2|м|л|т|LUT|ШТ)"


def normalize(t: str) -> str:
    """Типовой шум tesseract на формах УПД/СФ."""
    t = t.replace("\u00a0", " ").replace("\u202f", " ")
    t = re.sub(r"\b(?:N[oо°ºe]|Ne|Мо|М°)\s*(?=\S)", "№ ", t)
    t = re.sub(r"\bN[oо°ºe]\b\.?", "№", t)
    t = re.sub(r"ИНН\s*[И/|lI1]?\s*КПП", "ИНН/КПП", t)
    t = re.sub(r"(\d)\s*/\s*(\d)", r"\1/\2", t)
    # латиница/«@» внутри кодов вида BB-2026, ип-@ТЛ/ВВ
    t = re.sub(r"\b([A-Za-zА-Яа-я@]{1,4})(?=[-/]\s*(?:\d|[A-ZА-Я@]))",
               lambda m: m.group(1).replace("@", "К").upper().translate(LAT), t)
    t = re.sub(r"(?<=[A-ZА-Я\-/])@|@(?=[A-ZА-Я\-/])", "К", t)
    t = re.sub(r"(?<=\d)\s*-\s*(?=\d{1,3}\b)", "-", t) if False else t
    t = re.sub(r"Статус\s*[:\[\|(]*\s*([12])\s*[\]\|)]?", r"Статус: \1", t)
    return t


def _cell_num(c: str) -> Optional[float]:
    c = c.strip().strip("|[]").strip()
    if not re.fullmatch(r"\d{1,4}(?: \d{3})*(?:[.,]\d{1,3})?", c):
        return None
    return float(c.replace(" ", "").replace(",", "."))


def _cells(line: str) -> List[str]:
    return [c for c in re.split(r"\s{2,}|\|", line) if c.strip()]


def _tokens(line: str):
    return [(m.start(), m.end(), m.group(0)) for m in re.finditer(r"\d+(?:[.,]\d+)?", line)]


def _segment(line: str, merges):
    """Числа строки при заданном наборе склеек «группа тысяч» (merges[i] — клеить токен i+1 к i)."""
    toks, out = _tokens(line), []
    for i, (st, en, tx) in enumerate(toks):
        if i and merges[i - 1]:
            pst, _, ptx = out[-1]
            out[-1] = (pst, en, ptx + tx)
        else:
            out.append((st, en, tx))
    return [(st, float(tx.replace(",", ".")), bool(re.search(r"[.,]\d{2}$", tx))) for st, en, tx in out]


def _mergeable(line: str):
    toks = _tokens(line)
    res = []
    for i in range(len(toks) - 1):
        (s1, e1, t1), (s2, e2, t2) = toks[i], toks[i + 1]
        res.append(line[e1:s2] == " " and re.fullmatch(r"\d{1,4}", t1) is not None and re.fullmatch(r"\d{3}(?:[.,]\d{1,2})?", t2) is not None)
    return res


def numbers(line: str):
    """-> (triple|None, все числа). triple = (idx, qty, price, sum, pos) — ищется по кол-во × цена = сумма среди вариантов склейки."""
    can = _mergeable(line)
    idx = [i for i, c in enumerate(can) if c]
    greedy = _segment(line, can)
    if len(idx) > 10:
        idx = idx[:10]
    best = None
    for mask in range(1 << len(idx)):
        merges = [False] * len(can)
        for j, i in enumerate(idx):
            merges[i] = bool(mask >> j & 1)
        nums = _segment(line, merges)
        for k in range(len(nums) - 2):
            q, p, sm = nums[k][1], nums[k + 1][1], nums[k + 2][1]
            # сумма (гр. 5) в форме всегда с копейками; кол-во × цена должно сойтись
            if q > 0 and p > 0 and sm >= 1 and nums[k + 2][2] and abs(q * p - sm) < 0.05 + 1e-6 * sm:
                rest_pos = nums[k + 2][0]
                rest = [v for st, v, dec in greedy if st > rest_pos and dec]
                cand = (k, q, p, sm, nums[k][0], rest)
                if best is None or sm > best[3]:
                    best = cand
                break
    return best, greedy


HEAD_WORDS = set("""товара товаров вида изм изме един единица единицу измерения обозначение обозна условное объем объём тариф тари
код номер наименование описание выполненных оказанных работ услуг имущественного права количество цена стоимость
налога налоговая ставка сумма акциза страна происхождения краткое цифровой декларации регистрационный рег всего
чение нацио нальное""".split())


def _name_words(s: str) -> str:
    return " ".join(w for w in re.findall(r"[А-ЯЁа-яё][А-ЯЁа-яё\-]{2,}", s)
                    if w.lower() not in HEAD_WORDS and w.lower() not in ("акциза", "без", "чел", "шт"))


def rows(text: str) -> Tuple[List[dict], str]:
    L = text.splitlines()
    start, how = None, ""
    for i, ln in enumerate(L):
        if re.search(r"^\s*А\s+[1lБ]\s+", ln) or re.search(r"^\s*А\s+Б\s+1\b", ln):
            start, how = i + 1, "ряд номеров граф"
            break
    if start is None:
        for i, ln in enumerate(L):
            if re.search(r"Наименование", ln) and i > 5:
                start, how = i + 1, "заголовок «Наименование»"
                break
    start = start or 0
    out, buf, after = [], [], False
    for ln in L[start:]:
        if re.search(r"Всего\s+к\s+оплате", ln):
            break
        tr, allnums = numbers(ln)
        loose = None
        if not tr and re.search(OUR_UNITS + r"\.?\s", ln, re.I):
            mu0 = re.search(OUR_UNITS + r"\.?\s", ln, re.I)
            nn = [v for st, v, dec in allnums if st > mu0.start()]
            if len(nn) >= 3 and sum(1 for st, v, dec in allnums if st > mu0.start() and dec) >= 2:
                loose = (nn, mu0.start())
        if not tr and not loose:
            if not ln.strip():
                after = False
            frag = _name_words(ln[:int(len(ln) * 0.45)])
            if frag:
                if out and after:
                    out[-1]["name"] = (out[-1]["name"] + " " + frag).strip()
                else:
                    buf.append(frag)
            continue
        if tr:
            k, q, p, s, pos, rest = tr
            ok = True
        else:
            (nn, pos) = loose
            q, p, s = nn[:3]
            ok = abs(q * p - s) < 0.05
            rest = nn[3:]
        left = re.sub(r"^\s*\S{0,3}\s*\d{1,3}\s*\|?", " ", ln[:pos])
        frag = _name_words(left)
        if frag:
            buf.append(frag)
        tail = ln[pos:]
        mr = re.search(r"(\d{1,2})\s*%", tail)
        rate = f"{mr.group(1)}%" if mr else ("Без НДС" if re.search(r"без\s*НДС", tail, re.I) else "")
        vat, s9 = None, None
        vat, s9 = None, None
        cand9 = [x for x in rest if x >= s - 0.05]
        if cand9:
            s9 = cand9[-1]
            vat = round(s9 - s, 2)
            if mr and vat > 0:
                vv = [x for x in rest if abs(x - vat) < 0.05]
                vat = vv[0] if vv else vat
        if not mr and vat:
            ratio = vat / s * 100 if s else 0
            std = [r_ for r_ in (5, 7, 10, 18, 20, 22) if abs(ratio - r_) < 0.2]
            if std:
                rate = f"{std[0]}%"
            else:  # графа 9 неразборчива (лишняя цифра) — без ставки НДС считаем сумму без НДС
                vat, s9 = 0.0, s
        if not rate and not vat:
            rate = "Без НДС"
        if rate == "Без НДС":
            vat, s9 = 0.0, s9 if s9 is not None else s
        out.append({"line_no": len(out) + 1, "name": " ".join(buf).strip(), "unit": "", "qty": q, "price": p,
                    "sum_without_vat": money(s), "vat_rate": rate, "vat_sum": money(vat) if vat is not None else "",
                    "sum_with_vat": money(s9) if s9 is not None else "", "qty_price_ok": ok})
        mu = re.search(r"(?<![А-Яа-яA-Za-z])" + OUR_UNITS + r"\.?(?=\s)", ln, re.I)
        out[-1]["unit"] = mu.group(0) if mu else ""
        buf, after = [], True
    return out, how


def totals(text: str) -> Dict:
    m = re.search(r"Всего\s+к\s+оплате(?:\s*\(9\))?([^\n]*)", text)
    if not m:
        return {}
    nn = [v for _, v, dec in _segment(m.group(1), _mergeable(m.group(1))) if dec]
    if not nn:
        return {}
    r = {"total_without_vat": money(nn[0]), "total_with_vat": money(nn[-1])}
    if len(nn) >= 3:
        r["total_vat"] = money(nn[-2])
    elif len(nn) == 2:
        r["total_vat"] = money(round(nn[1] - nn[0], 2))
    else:
        r["total_vat"] = ""
    return r


def extras(text: str) -> Dict[str, str]:
    r = {}
    m = re.search(r"Статус:\s*([12])\b", text)
    if m:
        r["upd_status"] = m.group(1)
    m = re.search(r"Договор\s*№?\s*(\S+)\s+от\s+(\d{1,2})\b[\s\S]{0,200}?\b(" + "|".join(MONTHS) + r")\s+(\d{4})", text, re.I)
    if not m:
        m = re.search(r"Договор\s*№?\s*(\S+)\s+от\s+(\d{1,2})\.(\d{2})\.(\d{4})", text, re.I)
        if m:
            r["contract_number"], r["contract_date"] = m.group(1).strip("№ "), f"{int(m.group(2)):02d}.{m.group(3)}.{m.group(4)}"
            m = None
    if m and m.group(3).lower() in MONTHS:
        r["contract_number"] = m.group(1).strip("№ ")
        r["contract_date"] = f"{int(m.group(2)):02d}.{MONTHS[m.group(3).lower()]:02d}.{m.group(4)}"
    m = re.search(r"Сч[её]т-фактура\s*№\s*(\S+(?:\s*-\s*\S+)?)\s+от\s+(\d{1,2})\s+([а-я]+)\s+(\d{4})", text, re.I)
    if m and m.group(3).lower() in MONTHS:
        r["doc_number"] = re.sub(r"\s*-\s*", "-", m.group(1))
        r["doc_date"] = f"{int(m.group(2)):02d}.{MONTHS[m.group(3).lower()]:02d}.{m.group(4)}"
    return r


def apply(card: dict, text: str, warnings: List[str]) -> dict:
    """Дополняет карточку, прочитанную text-layer читалкой по OCR-слою."""
    for k, v in extras(text).items():
        if v and not card.get(k):
            card[k] = v
    for k in ("doc_number", "contract_number"):
        if card.get(k):
            card[k] = re.sub(r"\s*-\s*", "-", card[k])
            card[k] = re.sub(r"\b([A-Z]{1,4})(?=-)", lambda m: m.group(1).translate(LAT), card[k])
    from .merge import inn_ok
    for role, mark in (("seller", "[14]"), ("buyer", "[19]")):
        if not card.get(f"{role}_inn"):
            nm = (card.get(f"{role}_name") or "").replace('"', " ").split()
            key = next((w for w in nm if len(w) > 4 and w.upper() not in ("ООО", "ИП", "АО", "ПАО")), "")
            for ln in text.splitlines():
                if mark in ln or (key and key in ln and re.search(r"ИНН\s*\d", ln)):
                    seg = ln[:ln.find(mark)] if role == "seller" else ln
                    c = [x for x in re.findall(r"\b(\d{10}|\d{12})\b", seg) if inn_ok(x)]
                    if role == "buyer":
                        c = c[-1:]
                    if c and c[0] != card.get("seller_inn" if role == "buyer" else "buyer_inn"):
                        card[f"{role}_inn"] = c[0]
                        warnings.append(f"ИНН {'продавца' if role == 'seller' else 'покупателя'} взят из блока подписей {mark}")
                        break
    if card.get("seller_inn") and card["seller_inn"] == card.get("buyer_inn"):
        warnings.append("ИНН продавца на скане неразборчив (совпал с ИНН покупателя) — поле очищено")
        card["seller_inn"], card["seller_kpp"] = "", ""
    lines_ok = card.get("lines") and all(l.get("qty") not in ("", None) for l in card["lines"])
    if not lines_ok:
        rs, how = rows(text)
        if rs:
            card["lines"] = rs
            warnings.append(f"строки таблицы прочитаны по OCR-тексту ({how or 'по цепочке чисел'}), наименования проверьте")
    for l in card.get("lines") or []:
        if l.get("qty_price_ok") is False:
            warnings.append(f"строка {l['line_no']}: кол-во × цена ≠ сумма — цифры на скане неразборчивы")
    t = totals(text)
    consistent = lambda d: all(d.get(k) not in ("", None) for k in ("total_without_vat", "total_vat", "total_with_vat")) and \
        abs(float(d["total_without_vat"]) + float(d["total_vat"]) - float(d["total_with_vat"])) < 0.05
    if t and consistent(t) and not consistent(card):
        card.update(t)
    for k, v in t.items():
        if card.get(k) in ("", None):
            card[k] = v
    # сверка граф 5 / 8 / 9 при НДС
    ls = card.get("lines") or []
    if ls and card.get("total_with_vat") not in ("", None):
        s5 = round(sum(float(l.get("sum_without_vat") or 0) for l in ls), 2)
        s8 = round(sum(float(l.get("vat_sum") or 0) for l in ls), 2)
        if card.get("total_without_vat") not in ("", None) and abs(s5 - float(card["total_without_vat"])) > 0.05:
            warnings.append(f"сумма строк без НДС (гр. 5) {s5} ≠ итогу {card['total_without_vat']}")
        if card.get("total_vat") not in ("", None) and abs(s8 - float(card["total_vat"])) > 0.05:
            warnings.append(f"сумма НДС строк (гр. 8) {s8} ≠ итогу НДС {card['total_vat']}")
        for l in ls:
            if l.get("sum_with_vat") in ("", None) and l.get("sum_without_vat") not in ("", None):
                l["sum_with_vat"] = money(float(l["sum_without_vat"]) + float(l.get("vat_sum") or 0))
    return card
