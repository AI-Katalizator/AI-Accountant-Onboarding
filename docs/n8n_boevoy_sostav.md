# Что реально стоит в боевом n8n Виктории (снято 28.10.2026)

Источник: контейнер `n8n_1`, образ **`n8nio/n8n:2.39.5`** (официальный, без своей сборки), compose `/Users/vikkey/n8n-compose/docker-compose.yml`, том `~/.n8n`.

## 1. Excel / xlsx — две разные вещи

| Что | Где | Зачем |
|---|---|---|
| `@e965/xlsx` | Уже лежит **внутри** официального образа n8n 2.39.5 (зависимость n8n). Отдельно `npm install` в Dockerfile **не нужен** и ломается. | Code-узел может собрать Excel, если в compose включено `NODE_FUNCTION_ALLOW_EXTERNAL=@e965/xlsx`. |
| Таблица реквизитов к задаче | Часто делает **docreader** (Python `openpyxl`, поле `merge_xlsx`) | Файл `Таблица_реквизитов_….xlsx` прикладывается к задаче. |

Вывод для упаковки: не вшивать xlsx через npm в образ. Достаточно официального n8n + одной строки в environment. Excel к задаче = ещё и рабочий docreader.

## 2. Разрешения (environment), без которых «не симпатично»

Из боевого compose:

- `NODE_FUNCTION_ALLOW_EXTERNAL=@e965/xlsx` — разрешить Code брать Excel-библиотеку.
- `NODES_EXCLUDE=["n8n-nodes-base.executeCommand"]` — запрет Execute Command; при этом Local File Trigger доступен.
- `GENERIC_TIMEZONE` / `TZ` = `Europe/Moscow`.

## 3. Кастомные / community-ноды, которые реально нужны продукту

Стоят в томе `~/.n8n/nodes` (не в образе). По сценариям бухгалтера используются:

| Пакет | Нода | Зачем |
|---|---|---|
| `n8n-nodes-ai-accountant-files` (свой, `local-nodes`) | Safe File Move | Безопасный перенос файлов между папками |
| `@prokodo/n8n-nodes-pdf-toolkit` | PDF Toolkit | Работа с PDF в ЦОД / поступлениях |

В `~/.n8n/nodes` также стоят Bitrix, Yandex Disk, Kie, Max, MCP, Tesseract, pdf-toolkit-v2 и др. — в сценариях продукта почти не участвуют (это другие проекты на том же n8n). В клиентский пакет их **не** тащим.

## 4. Как у вас это «подключалось»

Не отдельным Dockerfile n8n, а так:

1. Официальный образ `n8nio/n8n:2.39.5`.
2. Том `~/.n8n` — база, credentials, папка `nodes` с community-пакетами.
3. Строки environment в compose.
4. Свой SafeFileMove лежит в `~/.n8n/local-nodes` и подключён через `file:../local-nodes/...` в `nodes/package.json`.

## 5. Что должен делать установщик клиента

1. Поднять **официальный** n8n 2.39.5 (или тонкий тег `ai-accountant/n8n:2.39.5` = тот же FROM без npm).
2. Прописать environment как выше.
3. Положить в `~/.n8n/nodes` минимум: SafeFileMove + `@prokodo/n8n-nodes-pdf-toolkit` (версии зафиксировать).
4. Поднять docreader (Excel реквизитов) + Ollama.
5. Сценарии — отдельным шагом после профиля.

