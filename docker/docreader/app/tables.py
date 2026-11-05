# -*- coding: utf-8 -*-
"""Таблицы по координатам слов (pdfplumber, MIT).

Два способа:
1) colnum_table — формы с пронумерованными графами (УПД / счёт-фактура «А Б 1 1а …»,
   ТОРГ-12 «1 2 3 … 15»). Границы граф берутся по вертикальным линиям сетки,
   а если сетки нет — по серединам между номерами граф. Строки — по горизонтальным
   линиям сетки, а без сетки — по номеру строки в графе «А» (или «1» у ТОРГ-12).
   Продолжение строки на следующей странице приклеивается к предыдущей строке.
2) label_table — свободные таблицы (акты): шапка ищется по словам «Наименование»,
   «Кол-во», «Цена», «Сумма» через pdfplumber.extract_tables().
"""
import bisect
import re
from typing import Dict, List, Optional

from .util import clean

ORDER = ["А", "Б", "1", "1а", "1б", "2", "2а", "3", "4", "5", "6", "7", "8", "9",
         "10", "10а", "11", "12", "12а", "13", "14", "15", "16", "17"]
IDS = set(ORDER)
STOP_RE = re.compile(
    r"^(Всего\s+к\s+оплате|Всего\s+по\s+накладной|Итого|Передан\s+через|Страница\s+\d|Руководитель|"
    r"Главный\s+бухгалтер|Документ\s+составлен|Универсальный\s+передаточный\s+документ\s*№|"
    r"Товарная\s+накладная\s+имеет|Индивидуальный\s+предприниматель|Основани[ея]\s+передачи)", re.I)


def _tok(t: str) -> str:
    t = t.strip().replace("A", "А").replace("a", "а").replace("B", "Б")
    return t


def lines_of(words, tol=3.0):
    """Слова -> строки (по y). Возвращает [(top, bottom, [words отсортированы по x])]."""
    rows = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if rows and abs(rows[-1][0] - w["top"]) <= tol:
            rows[-1][2].append(w)
            rows[-1][1] = max(rows[-1][1], w["bottom"])
        else:
            rows.append([w["top"], w["bottom"], [w]])
    for r in rows:
        r[2].sort(key=lambda w: w["x0"])
    return rows


def find_colnum_row(words):
    """Строка номеров граф. Возвращает (kind, [words]) или None. kind: 'upd' | 'torg12'."""
    best = None
    for top, bottom, ws in lines_of(words):
        toks = [_tok(w["text"]) for w in ws]
        ids = [t for t in toks if t in IDS]
        if len(ids) < 6 or len(ids) < len(toks) - 1:
            continue
        idx = [ORDER.index(t) for t in ids]
        if idx != sorted(idx) or len(set(ids)) != len(ids):
            continue
        hw = [w for w in ws if _tok(w["text"]) in IDS]
        kind = "upd" if "А" in ids else ("torg12" if ids[:4] == ["1", "2", "3", "4"] else (
            "sf" if ids[0] == "1" and "1а" in ids and "5" in ids and "9" in ids else ""))
        if not kind:
            continue
        if best is None or len(hw) > len(best[1]):
            best = (kind, hw)
    return best


def _merge(xs, gap=2.0):
    out = []
    for x in sorted(xs):
        if not out or x - out[-1] > gap:
            out.append(x)
    return out


def _vbounds(page, y, hdr):
    xs = [e["x0"] for e in page.edges if e["orientation"] == "v" and e["top"] - 1 <= y <= e["bottom"] + 1]
    xs = _merge(xs)
    # сетка годится, если почти каждый номер графы попал в свой промежуток
    if len(xs) >= len(hdr):
        slots = [bisect.bisect(xs, (w["x0"] + w["x1"]) / 2) for w in hdr]
        if len(set(slots)) == len(slots):
            return xs, True
    c = [(w["x0"] + w["x1"]) / 2 for w in hdr]
    return [-1e9] + [(c[i] + c[i + 1]) / 2 for i in range(len(c) - 1)] + [1e9], False


def _nogrid_candidates(hdr):
    """Без сетки граница графы неизвестна: пробуем середины между номерами и левые края номеров."""
    c = [(w["x0"] + w["x1"]) / 2 for w in hdr]
    mid = [-1e9] + [(c[i] + c[i + 1]) / 2 for i in range(len(c) - 1)] + [1e9]
    left = [-1e9] + [w["x0"] - 1.5 for w in hdr[1:]] + [1e9]
    return [mid, left]


NUMERIC_COLS = {"upd": ["3", "4", "5", "8", "9"], "torg12": ["10", "11", "12", "14", "15"]}
NUM_CELL = re.compile(r"^-?\d{1,3}(?:[ \u00a0]\d{3})*(?:[.,]\d+)?$|^-?\d+(?:[.,]\d+)?$|^(без НДС|--|-|x|х|X|Х)$", re.I)


def _score(layout, body):
    """Сколько ячеек числовых граф выглядят как одно число (а не склейка/обрывок)."""
    cells = {}
    for w in body:
        cells.setdefault((round(w["top"]), layout.col(w)), []).append(w["text"])
    sc = 0
    for (y, col), ws in cells.items():
        if col in NUMERIC_COLS.get(layout.kind, []):
            sc += 1 if NUM_CELL.match(" ".join(ws)) else -2
    return sc


def _hlines(page, x0, x1, y0, y1):
    ys = [e["top"] for e in page.edges if e["orientation"] == "h" and y0 - 1 <= e["top"] <= y1 + 1
          and e["x0"] <= x0 + 30 and e["x1"] >= x1 - 30]
    return _merge(ys, 1.5)


def _stop_y(words, y0, page_h):
    for top, bottom, ws in lines_of([w for w in words if w["top"] > y0]):
        txt = " ".join(w["text"] for w in ws)
        # стоп-слово должно стоять в начале «логической» строки: ищем его в любом месте строки
        for i in range(len(ws)):
            if STOP_RE.match(" ".join(w["text"] for w in ws[i:i + 6])):
                return top, txt
    return page_h, ""


class ColLayout:
    def __init__(self, kind, bounds, slot_names, grid, x0, x1):
        self.kind, self.bounds, self.slot_names, self.grid, self.x0, self.x1 = kind, bounds, slot_names, grid, x0, x1
        self.fieldmap = {}

    def col(self, w) -> str:
        return self.slot_names.get(bisect.bisect(self.bounds, (w["x0"] + w["x1"]) / 2), "?")


def _cells(layout, ws):
    """Ячейки строки. Перенос строки внутри ячейки помечается:
    «\u00ad» — строка заполнена до правого края графы (возможен перенос посреди слова, как в Диадоке),
    «\n» — строка короткая (обычный перенос по словам)."""
    cells: Dict[str, List[dict]] = {}
    for w in sorted(ws, key=lambda w: (round(w["top"]), w["x0"])):
        cells.setdefault(layout.col(w), []).append(w)
    out = {}
    for k, v in cells.items():
        parts, prev = [], None
        for w in v:
            if prev is not None:
                if w["top"] - prev["top"] > 3:
                    i = bisect.bisect(layout.bounds, (prev["x0"] + prev["x1"]) / 2)
                    right = layout.bounds[i] if i < len(layout.bounds) else layout.x1
                    cw = (prev["x1"] - prev["x0"]) / max(len(prev["text"]), 1)
                    parts.append("\u00ad" if right - prev["x1"] < 3.5 * cw else "\n")
                else:
                    parts.append(" ")
            parts.append(w["text"])
            prev = w
        out[k] = "".join(parts)
    return out


SERVICE_RX = re.compile(r"^Для1С_|^ИзмеренияКод:|##,?$")


def drop_service_text(words):
    """Служебный текст 1С поверх таблицы («Для1С_Идентификатор: …») печатается своим цветом — убираем весь этот цвет."""
    bad = {str(w.get("non_stroking_color")) for w in words if SERVICE_RX.search(w["text"])}
    if not bad:
        return words
    return [w for w in words if str(w.get("non_stroking_color")) not in bad]


def colnum_table(pdf) -> Optional[dict]:
    """Таблица формы с пронумерованными графами по всем страницам."""
    layout = None
    rows: List[dict] = []
    totals_cells: List[dict] = []
    totals_text = []
    pages_used = []
    finished = False
    for pno, page in enumerate(pdf.pages, 1):
        if finished:
            break
        words = drop_service_text(page.extract_words(x_tolerance=1.5, keep_blank_chars=False,
                                                     extra_attrs=["non_stroking_color"]))
        if not words:
            continue
        found = find_colnum_row(words)
        if found:
            kind, hdr = found
            yh = (hdr[0]["top"] + hdr[0]["bottom"]) / 2
            bounds, grid = _vbounds(page, yh, hdr)
            y0 = max(w["bottom"] for w in hdr) + 0.5
            cands = [bounds] if grid else _nogrid_candidates(hdr)
            best = None
            for b in cands:
                slot = {bisect.bisect(b, (w["x0"] + w["x1"]) / 2): _tok(w["text"]) for w in hdr}
                lay = ColLayout(kind, b, slot, grid, min(w["x0"] for w in hdr), max(w["x1"] for w in hdr))
                yst, _ = _stop_y(words, y0, page.height)
                sc = _score(lay, [w for w in words if y0 < w["top"] < yst])
                if best is None or sc > best[0]:
                    best = (sc, lay)
            layout = best[1]
            labels = header_labels(page, words, layout, min(w["top"] for w in hdr))
            layout.fieldmap, layout.fieldmap_src = map_fields(kind, labels, [_tok(w["text"]) for w in hdr])
        elif layout is not None:
            y0 = 0  # продолжение таблицы на следующей странице без шапки
        else:
            continue
        y1, stop_txt = _stop_y(words, y0, page.height)
        body = [w for w in words if y0 < w["top"] < y1 - 0.5]
        anchor_col = layout.fieldmap.get("line_no") or ("А" if layout.kind == "upd" else ("3" if layout.kind == "sf" else "1"))
        anchor_rx = r"\d{1,4}" if anchor_col != "3" else r"\d+(?:[.,]\d+)?"
        if found is None:
            body = [w for w in body if layout.x0 - 40 <= w["x0"] <= layout.x1 + 40]
        anchors = sorted(w["top"] for w in body
                         if layout.col(w) == anchor_col and re.fullmatch(anchor_rx, w["text"]))
        # верхняя граница ячейки над номером строки: горизонтальная линия, пересекающая графу «А»
        acol = [i for i, n in layout.slot_names.items() if n == anchor_col]
        hl = []
        if layout.grid and acol:
            i = acol[0]
            ax0 = layout.bounds[i - 1] if i - 1 >= 0 else layout.x0
            ax1 = layout.bounds[i] if i < len(layout.bounds) else ax0 + 10
            hl = _merge([e["top"] for e in page.edges if e["orientation"] == "h"
                         and e["x0"] <= ax0 + 2 and e["x1"] >= ax1 - 2 and y0 - 2 <= e["top"] <= y1 + 2], 1.0)

        def cell_top(y):
            above = [h for h in hl if h <= y + 0.5]
            return above[-1] - 0.3 if above else y - 2.5

        tops = [cell_top(a) for a in anchors]
        groups = []
        lead = [w for w in body if not tops or w["top"] < tops[0]]
        if lead and found is None:
            groups.append(lead)  # продолжение строки с предыдущей страницы
        for i, ys in enumerate(tops):
            ye = tops[i + 1] if i + 1 < len(tops) else y1
            groups.append([w for w in body if ys <= w["top"] < ye])
        for g in groups:
            cells = _cells(layout, g)
            anchor_col = layout.fieldmap.get("line_no") or anchor_col
            a = cells.get(anchor_col, "")
            if re.fullmatch(r"\d{1,4}", a.split(" ")[0] if a else ""):
                cells["_page"] = pno
                rows.append(cells)
            elif rows and any(v for k, v in cells.items()):
                # продолжение предыдущей строки (перенос внутри ячейки или на новую страницу)
                for k, v in cells.items():
                    rows[-1][k] = (rows[-1].get(k, "") + "\n" + v).strip("\n")
        pages_used.append(pno)
        below = " ".join(w["text"] for w in words if w["top"] >= y1 - 1)
        if re.search(r"(?i)Всего\s+(к\s+оплате|по\s+накладной)", below):
            finished = True
        # строка итогов
        if stop_txt and re.search(r"(?i)(Всего|Итого)", stop_txt):
            tw = [w for w in words if y1 - 1 <= w["top"] <= y1 + 40]
            prev_had_label = False
            for top, bottom, ws in lines_of(tw):
                t = " ".join(w["text"] for w in ws)
                is_label = bool(re.search(r"(?i)(Всего|Итого)", t))
                only_nums = bool(re.fullmatch(r"[\d\s.,xXхХ—-]+", t))
                if not (is_label or (prev_had_label and only_nums)):
                    break
                prev_had_label = is_label
                totals_text.append(t)
                totals_cells.append(_cells(layout, [w for w in ws if not re.match(r"(?i)(всего|итого|к|оплате|по|накладной|\(9\))$", w["text"])]))
    if layout is None:
        return None
    merged_tot: Dict[str, str] = {}
    for c in totals_cells:
        for k, v in c.items():
            if k != "?" and v:
                merged_tot.setdefault(k, v)
    return {"kind": layout.kind, "grid": layout.grid, "columns": list(layout.slot_names.values()),
            "fieldmap": layout.fieldmap, "fieldmap_src": getattr(layout, "fieldmap_src", ""),
            "rows": rows, "totals": merged_tot, "totals_text": totals_text, "pages": pages_used}


# ---------------------------------------------------------------- свободные таблицы (акты)
LABELS = [
    ("line_no", r"^№|^n\b|^№\s*п/?п"),
    ("vat_rate", r"ставк"),
    ("vat_sum", r"^ндс\s*\d{1,2}\s*%$|сумма\s+ндс|ндс,?\s*руб|^ндс$|в\s+т\.?\s*ч\.?\s+ндс|сумма\s+налога"),
    ("sum_without_vat", r"без\s+ндс|без\s+налога"),
    ("sum_with_vat", r"с\s+ндс|с\s+учетом\s+ндс|всего"),
    ("name", r"наименован|работ|услуг|товар|описан|содержан"),
    ("qty", r"кол-?\s*во|количеств|^кол"),
    ("unit", r"^ед|единиц"),
    ("price", r"цена|тариф|стоимость\s+ед"),
    ("sum", r"сумма|стоимость"),
]


def _map_header(cells):
    m = {}
    for i, c in enumerate(cells):
        t = clean(c).lower()
        if not t:
            continue
        for key, rx in LABELS:
            if key in m.values() and key != "sum":
                continue
            if re.search(rx, t):
                if key not in m.values():
                    m[i] = key
                break
    return m


def label_table(pdf) -> Optional[dict]:
    rows, mapping = [], None
    for pno, page in enumerate(pdf.pages, 1):
        tables = page.extract_tables() or []
        if not tables:
            tables = page.extract_tables({"vertical_strategy": "text", "horizontal_strategy": "text"}) or []
        for t in tables:
            for r in t:
                cells = [clean(c) for c in r]
                if mapping is None:
                    m = _map_header(cells)
                    vals = set(m.values())
                    if "name" in vals and ({"sum", "sum_with_vat", "sum_without_vat", "price"} & vals):
                        mapping = m
                    continue
                if not any(cells):
                    continue
                if _map_header(cells) and not any(re.search(r"\d", c) for c in cells):
                    continue  # повтор шапки на следующей странице
                d = {mapping[i]: cells[i] for i in mapping if i < len(cells)}
                first = clean(" ".join(cells[:2])).lower()
                if re.match(r"(итого|всего|в том числе|без налога)", first):
                    break
                if not d.get("name") and rows:
                    continue
                if d.get("name") and not any(re.search(r"\d", d.get(k, "")) for k in ("sum", "sum_with_vat", "sum_without_vat", "price", "qty")):
                    if rows:  # перенос наименования в отдельную строку таблицы
                        rows[-1]["name"] = clean(rows[-1]["name"] + " " + d["name"])
                    continue
                d["_page"] = pno
                rows.append(d)
        if mapping and rows:
            pass
    if mapping is None:
        return None
    return {"kind": "label", "columns": sorted(set(mapping.values())), "rows": rows}


# официальная разметка граф (если заголовки над номерами не прочитались)
OFFICIAL = {
    "upd": {"line_no": "А", "code": "Б", "name": "1", "unit_code": "2", "unit": "2а", "qty": "3", "price": "4",
            "sum_without_vat": "5", "excise": "6", "vat_rate": "7", "vat_sum": "8", "sum_with_vat": "9"},
    # форма без графы «Б» (Диадок/СБИС, ред. 2024): А — код товара, 1 — № п/п, 1а — наименование, 1б — код вида
    "upd_no_b": {"code": "А", "line_no": "1", "name": "1а", "unit_code": "2", "unit": "2а", "qty": "3", "price": "4",
                 "sum_without_vat": "5", "excise": "6", "vat_rate": "7", "vat_sum": "8", "sum_with_vat": "9"},
    # отдельный счёт-фактура (форма до 2024: 1 — наименование, 1а — код вида; без № п/п)
    "sf": {"name": "1", "unit_code": "2", "unit": "2а", "qty": "3", "price": "4",
           "sum_without_vat": "5", "excise": "6", "vat_rate": "7", "vat_sum": "8", "sum_with_vat": "9"},
    # счёт-фактура ред. 2024: 1 — № п/п, 1а — наименование, 1б — код вида
    "sf_2024": {"line_no": "1", "name": "1а", "unit_code": "2", "unit": "2а", "qty": "3", "price": "4",
                "sum_without_vat": "5", "excise": "6", "vat_rate": "7", "vat_sum": "8", "sum_with_vat": "9"},
    "torg12": {"line_no": "1", "name": "2", "code": "3", "unit": "4", "unit_code": "5", "qty": "10", "price": "11",
               "sum_without_vat": "12", "vat_rate": "13", "vat_sum": "14", "sum_with_vat": "15"},
}
FIELD_RX = [
    ("line_no", r"№\s*п/?п|^№$|номер\s+по\s+порядку|^но-?\s*мер"),
    ("excise", r"акциз"),
    ("vat_rate", r"ставка"),
    ("vat_sum", r"сумма\s+налога|сумма\s+ндс|предъявляемая"),
    ("sum_with_vat", r"с\s+налогом|с\s+учетом\s+ндс|с\s+уч[её]том"),
    ("sum_without_vat", r"без\s+налога|без\s+ндс|без\s+учета\s+ндс"),
    ("price", r"цена"),
    ("qty", r"количеств|коли\s*чество|масса\s+нетто"),
    ("name", r"наименование\s+товара|описание\s+выполненных|наименование,\s*характеристика"),
    ("unit", r"условное|обозначение"),
]


def header_labels(page, words, layout, y_hdr_top):
    """Тексты заголовков граф (над строкой номеров), по графам."""
    lab = {}
    for w in words:
        if y_hdr_top - 160 < w["top"] < y_hdr_top - 0.5 and layout.x0 - 40 <= w["x0"] <= layout.x1 + 40:
            c = layout.col(w)
            if c != "?":
                lab.setdefault(c, []).append(w)
    out = {}
    for c, ws in lab.items():
        t = " ".join(x["text"] for x in sorted(ws, key=lambda w: (round(w["top"]), w["x0"])))
        out[c] = re.sub(r"-\s+", "", t).lower().replace("ё", "е")
    return out


def map_fields(kind, labels, cols_present=()):
    if kind == "torg12":  # унифицированная форма ТОРГ-12 неизменна, а подписи граф многословные — берём номера граф
        return dict(OFFICIAL["torg12"]), "official"
    if kind == "sf":  # форма счёта-фактуры утверждена постановлением № 1137 — номера граф надёжнее подписей
        return dict(OFFICIAL["sf_2024" if "1б" in cols_present else "sf"]), "official"
    fm = {}
    for field, rx in FIELD_RX:
        for col, t in labels.items():
            if col in fm.values():
                continue
            if re.search(rx, t):
                fm[field] = col
                break
    off = OFFICIAL.get(kind, {})
    if kind == "upd" and "Б" not in cols_present and "1б" in cols_present:
        off = OFFICIAL["upd_no_b"]
    if kind == "sf" and "1б" in cols_present:
        off = OFFICIAL["sf_2024"]
    # если заголовки дали меньше половины граф — доверяем официальной разметке
    if len([k for k in ("line_no", "name", "qty", "price", "sum_with_vat") if k in fm]) < 3:
        return dict(off), "official"
    for k, v in off.items():
        if k not in fm and v not in fm.values():
            fm[k] = v
    return fm, "labels"
