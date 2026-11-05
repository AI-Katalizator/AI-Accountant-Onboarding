#!/usr/bin/env python3
"""Проверка заполненного профиля. Запуск: python3 validate_profile.py profile.json
Только читает файл. Ничего никуда не отправляет."""
import json, re, sys

SECRET_WORDS = ("password", "пароль", "token", "api_key", "apikey", "secret", "секрет")
REQUIRED = ["profile_id", "organization.name_display", "organization.inn",
            "organization.ref_guid", "onec.odata_base_url", "onec.http_credential_name",
            "folders.incoming_host", "folders.incoming_n8n", "task_settings.default_executor.ref_guid",
            "task_settings.due_days", "execution.timezone"]

def get(d, path):
    for k in path.split("."):
        if not isinstance(d, dict) or k not in d: return None
        d = d[k]
    return d

def inn_ok(inn):
    if not re.fullmatch(r"\d{10}|\d{12}", inn or ""): return False
    n = [int(c) for c in inn]
    c = lambda w: sum(a * b for a, b in zip(w, n)) % 11 % 10
    if len(n) == 10: return c([2,4,10,3,5,9,4,6,8]) == n[9]
    return c([7,2,4,10,3,5,9,4,6,8]) == n[10] and c([3,7,2,4,10,3,5,9,4,6,8]) == n[11]

def walk(d, pre=""):
    if isinstance(d, dict):
        for k, v in d.items(): yield from walk(v, f"{pre}{k}.")
    else: yield pre[:-1], d

def main(p):
    prof = json.load(open(p, encoding="utf-8"))
    prof = prof.get("profile", prof)
    errs = []
    for r in REQUIRED:
        if get(prof, r) in (None, "", []): errs.append(f"не заполнено: {r}")
    inn = get(prof, "organization.inn")
    if inn and not inn_ok(inn): errs.append("ИНН не проходит проверку контрольной цифры")
    kpp = get(prof, "organization.kpp")
    if kpp and not re.fullmatch(r"\d{4}[\dA-Z]{2}\d{3}", kpp): errs.append("КПП: неверный формат")
    guid = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    for k, v in walk(prof):
        if k.endswith("ref_guid") and v and not guid.match(str(v)): errs.append(f"{k}: не похоже на ссылку 1С")
        if any(w in k.lower() for w in SECRET_WORDS): errs.append(f"{k}: секретам в профиле не место")
        if k.startswith("folders.") and k.endswith("_n8n") and v and not str(v).startswith("/home/node/.n8n-files"):
            errs.append(f"{k}: путь внутри n8n должен начинаться с /home/node/.n8n-files")
    if errs:
        print("ПРОФИЛЬ НЕ ГОТОВ:"); [print(" -", e) for e in errs]; sys.exit(1)
    print("Профиль заполнен правильно.")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "profile.json")
