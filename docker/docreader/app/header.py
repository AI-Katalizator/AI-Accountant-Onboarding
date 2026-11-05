# -*- coding: utf-8 -*-
"""Реквизиты шапки и подвала по тексту страницы (regex), отдельно для каждого типа документа."""
import re
from typing import Dict, List

from .util import DATE_RE, clean, norm_date

INN_KPP = r"(\d{9,12})(?:\s*/\s*(\d{9}|[0-9A-ZА-Я]{9}))?"


def _first(patterns, text, flags=re.I | re.S):
    for p in patterns:
        m = re.search(p, text, flags)
        if m:
            return m
    return None


def _name(s: str) -> str:
    s = clean(s)
    s = re.sub(r"^[:|\s]+", "", s)
    s = re.sub(r"\s*\((?:\d[а-яa-z]?)\)\s*$", "", s)
    return s.strip(" ,;")


def _party_block(text: str, label: str, stop: str):
    """Блок «Исполнитель: ООО Ромашка, ИНН 7700000000, КПП 770001001, адрес…» (акты, договоры)."""
    m = re.search(label + r"\s*:?\s*(.{3,400}?)(?=" + stop + r"|\n\s*\n|$)", text, re.I | re.S)
    if not m:
        return "", "", ""
    block = clean(m.group(1))
    role = r"(?:\s+[а-яё]+)?"  # «ИНН/КПП исполнителя: …»
    inn = re.search(r"ИНН" + role + r"\s*:?\s*(\d{9,12})", block, re.I)
    kpp = re.search(r"КПП" + role + r"\s*:?\s*(\d{9})", block, re.I)
    ik = re.search(r"ИНН\s*/\s*КПП" + role + r"\s*:?\s*" + INN_KPP, block, re.I)
    name = re.split(r",?\s*(?:ИНН|ОГРН|КПП|адрес|юр\.|р/с|тел)", block, flags=re.I)[0]
    i = (ik.group(1) if ik else (inn.group(1) if inn else ""))
    k = (ik.group(2) if ik and ik.group(2) else (kpp.group(1) if kpp else ""))
    return _name(name), i or "", k or ""


def contract_from(text: str):
    """Номер и дата договора. Ищет и в «склеенном» тексте — для переносов вида «Дого вору №ФД-26»."""
    t = clean(text)
    m = re.search(r"(?:договор\w*|контракт\w*)(?:\s+(?:поставки|оказания\s+услуг|подряда|аренды|возмездного\s+оказания\s+услуг))?"
                  r"[^№\n]{0,40}?№\s*([A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9\-_/.]*?)\s*,?\s+от\s+" + DATE_RE, t, re.I)
    if m:
        return m.group(1).rstrip("."), norm_date(m.group(2))
    squeezed = re.sub(r"\s+", "", t)
    m = re.search(r"(?:[Дд]оговор|ДОГОВОР|[Кк]онтракт)[а-яА-Я]*№([A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9\-_/]*?)от(\d{1,2}\.\d{1,2}\.\d{2,4})", squeezed)
    if m:
        return m.group(1), norm_date(m.group(2))
    m = re.search(r"(?:договор\w*)\s+([A-Za-zА-Яа-яЁё0-9\-_/]*\d[A-Za-zА-Яа-яЁё0-9\-_/]*)\s+от\s+" + DATE_RE, t, re.I)
    if m:
        return m.group(1), norm_date(m.group(2))
    return "", ""


def payment_docs_from(s: str) -> str:
    s = clean(s)
    items = re.findall(r"№\s*([^\s,;]+)\s+от\s+" + DATE_RE, s)
    return ", ".join(f"№ {n} от {norm_date(d) or d}" for n, d in items)


def payment_numbers(s: str) -> List[str]:
    return [n for n, _ in re.findall(r"№\s*([^\s,;]+)\s+от\s+" + DATE_RE, s or "")]


def upd_header(text: str) -> Dict[str, str]:
    r: Dict[str, str] = {}
    m = _first([r"Сч[её]т-фактура\s*№\s*([^\n]{1,40}?)\s+от\s+" + DATE_RE,
                r"Универсальный\s+передаточный\s+документ\s*№\s*([^\n]{1,40}?)\s+от\s+" + DATE_RE], text)
    if m:
        r["doc_number"] = clean(m.group(1)).strip("№ ")
        r["doc_date"] = norm_date(m.group(2))
    m = _first([r"Статус\s*:?.{0,220}?документ\s*\(?[^)\n]{0,10}\)?\s*[—–-]\s*([12])\b", r"Статус\s*:?.{0,80}?[—–-]\s*([12])\b", r"Статус\s*:?\s*([12])\b"], text)
    r["upd_status"] = m.group(1) if m else ""
    m = _first([r"Продавец\s*:?\s*(.{1,250}?)\s*\(2\)"], text)
    r["seller_name"] = _name(m.group(1)) if m else ""
    m = _first([r"Покупатель\s*:?\s*(.{1,250}?)\s*\(6\)"], text)
    r["buyer_name"] = _name(m.group(1)) if m else ""
    s = _first([r"ИНН\s*/\s*КПП\s+продавца\s*:?\s*" + INN_KPP, r"ИНН\s*/\s*КПП\s*:?\s*" + INN_KPP + r"\s*\(2б\)"], text)
    b = _first([r"ИНН\s*/\s*КПП\s+покупателя\s*:?\s*" + INN_KPP, r"ИНН\s*/\s*КПП\s*:?\s*" + INN_KPP + r"\s*\(6б\)"], text)
    allik = re.findall(r"ИНН\s*/\s*КПП[^\d\n]{0,25}" + INN_KPP, text, re.I)
    if not s and allik:
        s = allik[0]
    if not b and len(allik) > 1:
        b = allik[1]

    def g(x, i):
        if x is None:
            return ""
        v = x.group(i) if hasattr(x, "group") else x[i - 1]
        return v or ""
    r["seller_inn"], r["seller_kpp"] = g(s, 1), g(s, 2)
    r["buyer_inn"], r["buyer_kpp"] = g(b, 1), g(b, 2)
    m = _first([r"К\s+платежно-расч[её]тному\s+документу\s*(.{0,300}?)\s*\(5\)"], text)
    r["payment_docs_raw"] = clean(m.group(1)) if m else ""
    r["payment_docs"] = payment_docs_from(r["payment_docs_raw"])
    m = _first([r"Основани[ея]\s+передачи\s*\(сдачи\)\s*/\s*получения\s*\(при[её]мки\)\s*(.{0,300}?)\s*(?:\(10\)|\[8\]|\n)"], text)
    r["basis"] = clean(m.group(1)) if m else ""
    return r


def act_header(text: str) -> Dict[str, str]:
    r: Dict[str, str] = {}
    m = _first([r"\bАкт\w*(?:\s+[а-яё\-]+){0,6}?\s*№\s*([^\s]{1,30})\s+от\s+" + DATE_RE,
                r"\bАКТ\b.{0,80}?№\s*([^\s]{1,30})\s+от\s+" + DATE_RE,
                r"\bАкт\w*(?:\s+[а-яё\-]+){0,6}?\s+от\s+" + DATE_RE], text[:3000])
    if m:
        if m.lastindex == 2:
            r["doc_number"], r["doc_date"] = clean(m.group(1)), norm_date(m.group(2))
        else:
            r["doc_number"], r["doc_date"] = "", norm_date(m.group(1))
    stop = r"(?<!КПП )(?<!ИНН )(?:Заказчик|Покупатель|Основание|Исполнитель|Подрядчик|№\s*п/?п|№\s+Наименование|Наименование)"
    r["seller_name"], r["seller_inn"], r["seller_kpp"] = _party_block(text, r"(?:Исполнитель|Подрядчик|Поставщик)", stop)
    r["buyer_name"], r["buyer_inn"], r["buyer_kpp"] = _party_block(text, r"(?:Заказчик|Покупатель)", stop)
    m = _first([r"Основание\s*:?\s*(.{0,200}?)(?:\n|$)"], text)
    r["basis"] = clean(m.group(1)) if m else ""
    r["upd_status"] = ""
    r["payment_docs"] = ""
    r["payment_docs_raw"] = ""
    return r


def torg12_header(text: str) -> Dict[str, str]:
    r: Dict[str, str] = {"upd_status": "", "payment_docs": "", "payment_docs_raw": ""}
    m = _first([r"Номер\s+документа\s+Дата\s+составления.{0,200}?\n\s*(?:ТОВАРНАЯ\s+НАКЛАДНАЯ\s+)?([^\s]{1,30})\s+(\d{2}\.\d{2}\.\d{4})",
                r"ТОВАРНАЯ\s+НАКЛАДНАЯ\s+([^\s]{1,30})\s+(\d{2}\.\d{2}\.\d{4})"], text)
    if m:
        r["doc_number"], r["doc_date"] = clean(m.group(1)), norm_date(m.group(2))
    for role, label in (("seller", r"\n\s*Поставщик"), ("buyer", r"\n\s*Плательщик")):
        m = re.search(r"(.{0,250}?)" + label + r"\s*(.{0,250}?)(?:\n|$)", text, re.S)
        block = clean((m.group(1).split("\n")[-1] + " " + m.group(2)) if m else "")
        inn = re.search(r"ИНН\s*(\d{10}|\d{12})", block)
        kpp = re.search(r"КПП\s*(\d{9})", block)
        r[role + "_name"] = _name(block.split(",")[0]) if block else ""
        r[role + "_inn"] = inn.group(1) if inn else ""
        r[role + "_kpp"] = kpp.group(1) if kpp else ""
    m = _first([r"Основание\s+(.{0,150}?)(?:\n|$)"], text)
    r["basis"] = clean(m.group(1)) if m else ""
    return r


def contract_doc_header(text: str) -> Dict[str, str]:
    r: Dict[str, str] = {"upd_status": "", "payment_docs": "", "payment_docs_raw": ""}
    m = _first([r"ДОГОВОР\w*(?:\s+[А-Яа-яЁё\-]+){0,5}?\s*№\s*([^\s]{1,30})", r"Договор\w*(?:\s+[а-яё\-]+){0,5}?\s*№\s*([^\s]{1,30})"], text[:1500], re.S)
    r["doc_number"] = clean(m.group(1)) if m else ""
    m = re.search(DATE_RE, text[:1500])
    r["doc_date"] = norm_date(m.group(1)) if m else ""
    inns = re.findall(r"ИНН\s*:?\s*(\d{10}|\d{12})", text)
    kpps = re.findall(r"КПП\s*:?\s*(\d{9})", text)
    r["party1_inn"] = inns[0] if inns else ""
    r["party2_inn"] = inns[1] if len(inns) > 1 else ""
    r["party1_kpp"] = kpps[0] if kpps else ""
    r["party2_kpp"] = kpps[1] if len(kpps) > 1 else ""
    r.update(contract_parties(text))
    m = re.search(r"(?:Предмет\s+договора|1\.1\.?)\s*(.{0,300}?)(?:\n\s*1\.2|\n\s*2\.|$)", text, re.S | re.I)
    r["subject"] = clean(m.group(1)) if m else ""
    return r


def poa_header(text: str) -> Dict[str, str]:
    r: Dict[str, str] = {"upd_status": "", "payment_docs": "", "payment_docs_raw": ""}
    m = _first([r"ДОВЕРЕННОСТЬ\s*№\s*([^\s]{1,30})", r"Доверенность\s*№\s*([^\s]{1,30})"], text[:1500])
    r["doc_number"] = clean(m.group(1)) if m else ""
    m = re.search(DATE_RE, text[:1500])
    r["doc_date"] = norm_date(m.group(1)) if m else ""
    m = re.search(r"(?:действительна|сроком|действует)\s+(?:до|по)\s+" + DATE_RE, text, re.I)
    m2 = re.search(r"(?:выдана|сроком)\s+(?:на\s+)?(\S+\s+(?:год|года|лет|месяц\w*))", text, re.I)
    r["valid_until"] = norm_date(m.group(1)) if m else (clean(m2.group(1)) if m2 else "")
    inns = re.findall(r"ИНН\s*:?\s*(\d{10}|\d{12})", text)
    r["principal_inn"] = inns[0] if inns else ""
    return r


ORG = r'((?:ООО|АО|ПАО|ЗАО|НАО|ОАО|ФГУП|МУП|ГУП|ИП)\s*[«"][^»"]{1,80}[»"]|(?:ИП|Индивидуальный\s+предприниматель)\s+[А-ЯЁ][а-яё\-]+\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?)'
SELLER_ROLES = r"(Исполнител|Поставщик|Подрядчик|Арендодател|Продав|Лицензиар)"
BUYER_ROLES = r"(Заказчик|Покупател|Арендатор|Лицензиат)"


def contract_parties(text: str) -> Dict[str, str]:
    """Стороны договора: «ООО "X" (ИНН …), именуемое «Исполнитель»»."""
    t = clean(text)
    out = {}
    for m in re.finditer(ORG + r"\s*[(,]?\s*(?:ИНН\s*:?\s*(\d{10}|\d{12}))?(?:\s*,?\s*КПП\s*:?\s*(\d{9}))?", t):
        tail = t[m.end():m.end() + 120]
        role = "seller" if re.search(SELLER_ROLES, tail) and not re.search(BUYER_ROLES, tail[:tail.find("Исполн") if "Исполн" in tail else len(tail)]) else (
            "buyer" if re.search(BUYER_ROLES, tail) else "")
        if role and role + "_name" not in out:
            out[role + "_name"] = clean(m.group(1))
            if m.group(2):
                out[role + "_inn"] = m.group(2)
            if m.group(3):
                out[role + "_kpp"] = m.group(3)
    return out


def sf_extra(text: str) -> Dict[str, str]:
    """Доп. поля отдельного счёта-фактуры (и УПД): исправление, грузоотправитель/получатель, документ об отгрузке, валюта."""
    r: Dict[str, str] = {}
    m = _first([r"Исправление\s*№\s*([^\n]{0,30}?)\s+от\s+([^\n]{0,20}?)\s*\(1а\)"], text)
    num_, dt = (clean(m.group(1)), clean(m.group(2))) if m else ("", "")
    r["correction_number"] = "" if re.fullmatch(r"[-—–\s]*", num_) else num_
    r["correction_date"] = "" if re.fullmatch(r"[-—–\s]*", dt) else dt
    for key, lab, n in (("shipper", r"Грузоотправитель\s+и\s+его\s+адрес", "3"), ("consignee", r"Грузополучатель\s+и\s+его\s+адрес", "4")):
        m = _first([lab + r"\s*:?\s*(.{0,250}?)\s*\(" + n + r"\)"], text)
        v = clean(m.group(1)) if m else ""
        r[key] = "" if re.fullmatch(r"[-—–\s]*", v) else v
    m = _first([r"Документ\s+об\s+отгрузке\s*(.{0,200}?)\s*\(5а\)"], text)
    r["shipping_doc"] = clean(m.group(1)) if m else ""
    m = _first([r"Валюта\s*:?\s*наименование,\s*код\s*(.{0,60}?)\s*\(7\)"], text)
    r["currency"] = clean(m.group(1)) if m else ""
    return r
