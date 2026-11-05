# -*- coding: utf-8 -*-
"""Тип документа по тексту: заголовок документа + маркеры из определений (classifier_rules.json)."""
import json
import os
import re
from typing import Dict, List, Tuple

DEF_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "definitions")

# doc_type (как в карточке v003) -> id определения
TYPE_DEF = {
    "УПД": "invoices_upd", "Счет-фактура": "invoices_sf", "ТОРГ-12": "invoices_upd",
    "Акт": "acceptance_certificates", "Договор": "commercial_contracts", "Доверенность": "powers_of_attorney",
}
DEF_TYPE = {"invoices_upd": "УПД", "invoices_sf": "Счет-фактура", "acceptance_certificates": "Акт",
            "commercial_contracts": "Договор", "powers_of_attorney": "Доверенность"}


def _markers() -> Dict[str, List[str]]:
    out = {}
    for d in DEF_TYPE:
        p = os.path.join(DEF_DIR, d, "classifier_rules.json")
        try:
            out[d] = [m.lower().replace("ё", "е") for m in json.load(open(p, encoding="utf-8")).get("text_markers", [])]
        except OSError:
            out[d] = []
    return out


MARKERS = _markers()

TITLE_PRIORITY = 50  # заголовки «Акт / Доверенность / Договор» (в коде)


def _type_rules() -> List[dict]:
    """type_rules из classifier_rules.json всех определений, по priority."""
    out = []
    for d in DEF_TYPE:
        p = os.path.join(DEF_DIR, d, "classifier_rules.json")
        try:
            for r in json.load(open(p, encoding="utf-8")).get("type_rules", []):
                out.append(dict(r, def_id=d))
        except OSError:
            pass
    return sorted(out, key=lambda r: r.get("priority", 100))


TYPE_RULES = _type_rules()


def _part(part: str, head: str) -> bool:
    part = part.strip()
    if part.startswith("re:"):
        return re.search(part[3:], head) is not None
    return part.lower().replace("ё", "е") in head


def sign_found(sign: str, head: str) -> bool:
    """Знак: «a + b» (плюс с пробелами) — все части сразу; «re:…» — регулярное выражение."""
    return all(_part(p, head) for p in sign.split(" + "))


def _apply(rule: dict, head: str):
    hit = next((s for s in rule.get("any", []) if sign_found(s, head)), None)
    if hit and not any(sign_found(s, head) for s in rule.get("none", [])):
        return hit
    return None


def classify(text: str) -> Tuple[str, str, List[str]]:
    """-> (doc_type, definition_id, reasons)."""
    t = (text or "").lower().replace("ё", "е")
    head = t[:3000]
    lines = [l.strip() for l in head.split("\n") if l.strip()][:25]
    reasons: List[str] = []
    hn = re.sub(r"\s+", " ", head)
    for r in [r for r in TYPE_RULES if r.get("priority", 100) < TITLE_PRIORITY]:
        hit = _apply(r, hn)
        if hit:
            reasons.append(f"{r.get('reason', r['type'])} (знак «{hit}»)")
            return r["type"], r["def_id"], reasons
    for l in lines:
        if re.match(r"^(акт|а\s*к\s*т)\b", l):
            reasons.append(f"заголовок: «{l[:60]}»")
            return "Акт", "acceptance_certificates", reasons
        if re.match(r"^доверенност", l):
            reasons.append(f"заголовок: «{l[:60]}»")
            return "Доверенность", "powers_of_attorney", reasons
        if re.match(r"^договор\b|^контракт\b", l):
            reasons.append(f"заголовок: «{l[:60]}»")
            return "Договор", "commercial_contracts", reasons
    for r in [r for r in TYPE_RULES if r.get("priority", 100) >= TITLE_PRIORITY]:
        hit = _apply(r, hn)
        if hit:
            reasons.append(f"{r.get('reason', r['type'])} (знак «{hit}»)")
            return r["type"], r["def_id"], reasons
    scores = {d: sum(1 for m in ms if m in t) for d, ms in MARKERS.items()}
    best = max(scores, key=scores.get) if scores else ""
    if best and scores[best] >= 2:
        reasons.append(f"маркеры определения {best}: {scores[best]}")
        return DEF_TYPE[best], best, reasons
    return "", "", ["тип документа не определён"]
