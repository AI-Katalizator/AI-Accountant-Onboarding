# -*- coding: utf-8 -*-
"""Общие мелочи: числа, даты, чистка строк."""
import re
from typing import Any, Optional

MONTHS = {
    "январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6,
    "июл": 7, "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
}
DATE_RE = r"(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}|\d{1,2}\s+[А-Яа-яЁё]+\s+\d{4}|«?\d{1,2}»?\s+[А-Яа-яЁё]+\s+\d{4})"


def clean(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def norm_date(s: str) -> str:
    """'29 декабря 2016 г.' / '1.6.26' / '«01» июня 2026' -> 'DD.MM.YYYY'. Пусто, если не распознано."""
    s = clean(s).replace("«", "").replace("»", "").replace('"', "")
    m = re.match(r"^(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})", s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
    else:
        m = re.match(r"^(\d{1,2})\s+([А-Яа-яЁё]+)\s+(\d{4})", s)
        if not m:
            return ""
        d, y = int(m.group(1)), int(m.group(3))
        w = m.group(2).lower()
        mo = 0
        for k in sorted(MONTHS, key=len, reverse=True):
            if w.startswith(k):
                mo = MONTHS[k]
                break
        if not mo:
            return ""
    if not (1 <= d <= 31 and 1 <= mo <= 12 and 1990 <= y <= 2100):
        return ""
    return f"{d:02d}.{mo:02d}.{y:04d}"


def num(s: Any) -> Optional[float]:
    """Число из ячейки: '6 245 177.05', '3 072,03', '9.98'. None для '--', 'x', 'без НДС'."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    t = str(s).replace("\u00a0", " ").replace("\u202f", " ").strip()
    t = re.sub(r"(?i)руб\.?|коп\.?|₽", "", t).strip()
    if not re.fullmatch(r"-?[\d\s]+([.,]\d+)?", t):
        return None
    t = t.replace(" ", "").replace(",", ".")
    try:
        return round(float(t), 4)
    except ValueError:
        return None


def money(x: Optional[float]):
    """Для карточки: число с 2 знаками или '' (как в v003)."""
    return "" if x is None else round(float(x), 2)


def norm_rate(s: Any) -> str:
    """Ставка НДС как напечатана: '22%', '10%', '0%', 'Без НДС', '22/122' или ''."""
    t = clean(s)
    if not t or t in ("--", "-", "—", "x", "х", "X", "Х"):
        return ""
    if re.search(r"(?i)без\s*(ндс|налога)", t):
        return "Без НДС"
    m = re.search(r"(\d{1,2}(?:[.,]\d+)?)\s*%", t)
    if m:
        return m.group(1).replace(",", ".") + "%"
    m = re.search(r"\b(\d{1,2}/1\d{2})\b", t)
    if m:
        return m.group(1)
    if re.fullmatch(r"\d{1,2}", t):
        return t + "%"
    return t


SHORT = {"в", "во", "на", "и", "по", "с", "со", "за", "к", "ко", "от", "для", "о", "об", "у", "из", "до", "не", "а", "г", "г.", "№"}


# частые слова первичных документов: «Дого|вору», «Меропри|ятий» — склеиваем, если кусок до переноса сам не слово
STEMS = ("договор", "мероприят", "заказчик", "исполнител", "организац", "проведен", "проходящ", "предоставлен",
         "обеспечен", "выступлен", "подготовк", "сентябр", "октябр", "ноябр", "декабр", "имуществ", "охран",
         "фотограф", "фотосъем", "обработк", "питани", "режим", "внутриобъект", "пропускн", "услуг", "оказан",
         "сопровожден", "оборудован", "аренд", "доставк", "техническ", "информацион", "консультац")


def join_wrapped(s: str, vocab=None) -> str:
    """Склейка переносов в узкой графе (Диадок переносит посреди слова без дефиса: «орга|низации»).
    Без словаря склеивать нельзя («Аренда|звукового» — два слова), поэтому склеиваем, только если
    склеенное слово целиком встречается в тексте этого же документа (vocab) или кусок кончается на «-».
    Иначе — пробел: «орга низации» читается и человеком, и моделью, а ложная склейка хуже."""
    vocab = vocab or set()
    out = ""
    for part in re.split(r"[\u00ad\n]", str(s or "")):
        part = part.strip()
        if not part:
            continue
        if not out:
            out = part
            continue
        last = out.split(" ")[-1]
        first = part.split(" ")[0]
        glued = re.sub(r"[^\wЁё-]", "", (last + first).lower())
        if last.endswith("-") and re.match(r"[а-яёА-ЯЁ0-9]", part):
            out += part
        elif re.search(r"[А-Яа-яЁё]$", last) and re.match(r"[а-яё]", first) and len(last) < 12 \
                and (glued in vocab or (glued.startswith(STEMS) and not last.lower().startswith(STEMS))):
            out += part
        else:
            out += " " + part
    return clean(out)


def vocab_of(text: str) -> set:
    return {w.lower() for w in re.findall(r"[А-Яа-яЁё]{5,}", text or "")}
