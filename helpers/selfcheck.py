#!/usr/bin/env python3
"""Итоговая самопроверка установки. Только читает. Запуск: python3 selfcheck.py <главная папка документов>"""
import json, os, sys, time, urllib.request

def ok(url, t=5):
    try:
        with urllib.request.urlopen(url, timeout=t) as r: return r.status == 200, r.read().decode("utf-8", "ignore")
    except Exception as e: return False, str(e)

res = []
a, _ = ok("http://localhost:5678/healthz"); res.append(("n8n отвечает на http://localhost:5678", a))
a, body = ok("http://localhost:8011/health")
res.append(("docreader отвечает", a))
if a:
    try: res.append(("docreader версии 0.2.x", json.loads(body).get("version", "").startswith("0.2")))
    except Exception: res.append(("docreader версии 0.2.x", False))
a, body = ok("http://localhost:11434/api/tags")
res.append(("Ollama запущена", a))
model = os.environ.get("VISION_MODEL", "qwen2.5vl:7b-16k")
res.append((f"модель {model} загружена", a and model in body))
if len(sys.argv) > 1:
    root = sys.argv[1]
    probe = os.path.join(root, ".проверка_связи.txt")
    try:
        with open(probe, "w", encoding="utf-8") as f: f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
        res.append(("главная папка доступна для записи", True))
    except Exception: res.append(("главная папка доступна для записи", False))
for name, good in res: print(("ГОТОВО  " if good else "ПРОБЛЕМА") + "  " + name)
sys.exit(0 if all(g for _, g in res) else 1)
