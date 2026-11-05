# -*- coding: utf-8 -*-
"""Жёсткие проверки карточки: контрольные цифры, арифметика, НДС, договор ≠ платёжка."""
import re
from typing import List

from .header import payment_numbers
from .sr.checksums import validate_inn


def _c(code, status, msg):
    return {"code": code, "status": status, "message": msg}


def _f(x):
    try:
        return None if x in ("", None) else float(x)
    except (TypeError, ValueError):
        return None


def run(card: dict) -> List[dict]:
    out: List[dict] = []
    dt = card.get("doc_type", "")
    # ИНН / КПП
    for role, title in (("seller", "продавца (исполнителя)"), ("buyer", "покупателя (заказчика)")):
        inn = re.sub(r"\D", "", str(card.get(role + "_inn", "")))
        if not inn:
            out.append(_c(f"{role}_inn", "error" if dt in ("УПД", "Акт", "ТОРГ-12", "Счет-фактура") else "skip", f"ИНН {title} не найден"))
        else:
            ok, msg = validate_inn(inn)
            out.append(_c(f"{role}_inn", "ok" if ok else "error",
                          f"ИНН {title} {inn}: " + ("контрольная цифра верна" if ok else "не проходит проверку ФНС (" + msg + ")")))
        kpp = str(card.get(role + "_kpp", "") or "")
        if kpp:
            ok = bool(re.fullmatch(r"\d{4}[0-9A-Z]{2}\d{3}", kpp))
            out.append(_c(f"{role}_kpp", "ok" if ok else "error", f"КПП {title} {kpp}: " + ("формат верный" if ok else "неверный формат (нужно 9 знаков)")))
        elif len(inn) == 10:
            out.append(_c(f"{role}_kpp", "warning", f"КПП {title} не найден (у организации он должен быть)"))
    # строки
    lines = card.get("lines") or []
    bad_math, bad_vat = [], []
    for l in lines:
        q, p, swo, vs, sw = (_f(l.get(k)) for k in ("qty", "price", "sum_without_vat", "vat_sum", "sum_with_vat"))
        if q and p:
            # в УПД/ТОРГ-12 цена — без налога (графа 4), в акте цена может включать НДС
            targets = [t for t in ((swo,) if dt in ("УПД", "ТОРГ-12", "Счет-фактура") and swo is not None else (swo, sw)) if t is not None]
            tol = lambda t: max(0.05, 0.0005 * t) + 0.01 * q
            if targets and not any(abs(q * p - t) <= tol(t) for t in targets):
                bad_math.append(f"строка {l.get('line_no')}: {q:g} × {p:g} = {q * p:.2f}, а в документе {targets[0]:.2f}")
        rate = str(l.get("vat_rate", ""))
        if rate == "Без НДС" and vs not in (None, 0.0):
            bad_vat.append(f"строка {l.get('line_no')}: «без НДС», но сумма налога {vs}")
        m = re.fullmatch(r"(\d+(?:\.\d+)?)%", rate)
        if m and swo is not None and vs is not None:
            exp = swo * float(m.group(1)) / 100
            if abs(exp - vs) > 1.0:
                bad_vat.append(f"строка {l.get('line_no')}: {rate} от {swo:.2f} = {exp:.2f}, а налог {vs:.2f}")
        if swo is not None and vs is not None and sw is not None and abs(swo + vs - sw) > 0.05:
            bad_vat.append(f"строка {l.get('line_no')}: {swo:.2f} + {vs:.2f} ≠ {sw:.2f}")
    if lines:
        out.append(_c("lines_qty_price", "error" if bad_math else "ok",
                      "; ".join(bad_math) if bad_math else "количество × цена = сумма во всех строках"))
        out.append(_c("lines_vat", "error" if bad_vat else "ok",
                      "; ".join(bad_vat) if bad_vat else "НДС в строках сходится со ставкой"))
    elif dt in ("УПД", "Акт", "ТОРГ-12", "Счет-фактура"):
        out.append(_c("lines", "error", "строки таблицы не найдены"))
    tw = _f(card.get("total_with_vat"))
    if lines and tw is not None:
        s = round(sum(_f(l.get("sum_with_vat")) or 0 for l in lines), 2)
        ok = abs(s - tw) < 0.05
        out.append(_c("lines_sum_total", "ok" if ok else "error",
                      f"сумма строк {s:.2f} " + ("= «Всего к оплате»" if ok else f"≠ «Всего к оплате» {tw:.2f}")))
    elif dt in ("УПД", "Акт", "ТОРГ-12", "Счет-фактура"):
        out.append(_c("total", "error", "итоговая сумма документа не найдена"))
    two, tv = _f(card.get("total_without_vat")), _f(card.get("total_vat"))
    if two is not None and tv is not None and tw is not None:
        ok = abs(two + tv - tw) < 0.05
        out.append(_c("totals_vat", "ok" if ok else "error",
                      f"итог без НДС {two:.2f} + НДС {tv:.2f} " + ("= итог с НДС" if ok else f"≠ итог с НДС {tw:.2f}")))
    # режим НДС
    rates = {str(l.get("vat_rate", "")) for l in lines if l.get("vat_rate") not in ("", None)}
    if "Без НДС" in rates and any(r.endswith("%") for r in rates):
        out.append(_c("vat_mode", "warning", "в одних строках «без НДС», в других ставка: " + ", ".join(sorted(rates))))
    if card.get("vat_mode") == "без НДС" and tv not in (None, 0.0):
        out.append(_c("vat_mode", "error", f"документ «без НДС», но итог НДС {tv}"))
    if "0%" in rates:
        out.append(_c("vat_zero", "warning", "ставка 0% — это не «без НДС»; 0% бывает при экспорте и т. п. Проверьте, что в документе напечатано именно 0%"))
    # договор ≠ платёжка
    cn = str(card.get("contract_number", "") or "")
    pays = payment_numbers(card.get("payment_docs", ""))
    if cn and cn in pays:
        out.append(_c("contract_vs_payment", "error", f"номер договора {cn} совпадает с номером платёжного документа — похоже, взят не тот номер"))
    elif cn:
        out.append(_c("contract_vs_payment", "ok", f"договор № {cn} не совпадает с платёжными документами"))
    # обязательные поля
    need = {"УПД": ["doc_number", "doc_date", "upd_status"], "Акт": ["doc_date"], "ТОРГ-12": ["doc_number", "doc_date"],
            "Счет-фактура": ["doc_number", "doc_date"], "Договор": ["doc_number", "doc_date"], "Доверенность": ["doc_date"]}
    miss = [k for k in need.get(dt, []) if not card.get(k)]
    if not dt:
        miss.append("doc_type")
    if dt == "УПД" and card.get("upd_status") not in ("1", "2") and "upd_status" not in miss:
        miss.append("upd_status")
    out.append(_c("required", "error" if miss else "ok", ("не найдены: " + ", ".join(miss)) if miss else "обязательные реквизиты найдены"))
    return out
