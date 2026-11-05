#!/usr/bin/env python3
"""Проверка связи с 1С через OData и видимости нужных объектов для пользователя AI.
Только ЧИТАЕТ (GET). Ничего не создаёт, не проводит и не удаляет.
Пароль клиент вводит сам в окне терминала; он не печатается и никуда не сохраняется.
Запуск: python3 check_odata.py http://localhost:8081/base/odata/standard.odata AI
Режим поиска: добавьте --find-org ИНН  или  --find-nomenclature "Оплата по счёту"  или  --users
"""
import base64, getpass, json, os, sys, urllib.error, urllib.parse, urllib.request

OBJECTS = ["Catalog_Контрагенты", "Catalog_ДоговорыКонтрагентов", "Catalog_Номенклатура",
           "Document_ПоступлениеТоваровУслуг", "Catalog_БанковскиеСчета",
           "Document_ПоступлениеНаРасчетныйСчет", "Document_СписаниеСРасчетногоСчета",
           "Document_ПлатежноеПоручение", "Document_СчетНаОплатуПоставщика"]

def get(base, auth, path, params=None):
    q = {"$format": "json", **(params or {})}
    url = base.rstrip("/") + "/" + urllib.parse.quote(path) + "?" + urllib.parse.urlencode(q, quote_via=urllib.parse.quote)
    req = urllib.request.Request(url, headers={"Authorization": "Basic " + auth})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))

def main():
    if len(sys.argv) < 3: print(__doc__); sys.exit(2)
    base, user = sys.argv[1], sys.argv[2]
    pw = os.environ.get("ONEC_PASSWORD") or getpass.getpass(f"Пароль пользователя {user} в 1С (не отображается): ")
    auth = base64.b64encode(f"{user}:{pw}".encode()).decode()
    del pw
    args = sys.argv[3:]
    try:
        if "--find-org" in args:
            inn = args[args.index("--find-org") + 1]
            r = get(base, auth, "Catalog_Организации", {"$filter": f"ИНН eq '{inn}'", "$select": "Ref_Key,Description,ИНН,КПП"})
            print(json.dumps(r.get("value", []), ensure_ascii=False, indent=1)); return
        if "--find-nomenclature" in args:
            name = args[args.index("--find-nomenclature") + 1]
            r = get(base, auth, "Catalog_Номенклатура", {"$filter": f"Description eq '{name}'", "$select": "Ref_Key,Description"})
            print(json.dumps(r.get("value", []), ensure_ascii=False, indent=1)); return
        if "--users" in args:
            r = get(base, auth, "Catalog_Пользователи", {"$select": "Ref_Key,Description", "$top": "200"})
            print(json.dumps(r.get("value", []), ensure_ascii=False, indent=1)); return
        get(base, auth, "", {})
        print("связь=да")
    except urllib.error.HTTPError as e:
        print("связь=нет", f"код={e.code}", "(401 — неверный логин или пароль; 404 — неверный адрес или OData не включён)"); sys.exit(1)
    except Exception as e:
        print("связь=нет", f"причина={e}"); sys.exit(1)
    missing = []
    for o in OBJECTS:
        try:
            get(base, auth, o, {"$top": "1", "$select": "Ref_Key"}); print(f"{o}=виден")
        except urllib.error.HTTPError as e:
            missing.append(o); print(f"{o}=НЕ виден (код {e.code})")
    if missing:
        print("\nНужно добавить в состав OData (обработка «Настройка автоматического REST-сервиса») или выдать права пользователю AI:")
        for o in missing: print(" -", o)
        sys.exit(1)
    print("\nВсе нужные объекты видны.")

if __name__ == "__main__":
    main()
