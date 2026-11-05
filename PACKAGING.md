# PACKAGING — Definition of Done упаковки установщика среды (05.11.2026)

## Что входит в поставку
- `SKILL.md` — диалоговый сценарий установки для ИИ-агента; `README.md`; `BUILD_NOTES.md`; этот файл.
- `docker/` — `docker-compose.yml`, `.env.example` (без секретов), тонкий `n8n/Dockerfile` = `FROM n8nio/n8n:2.39.5` без `npm install`; `docreader/` 0.2.0 (исходники + Dockerfile).
- `n8n-extras/` — своя нода Safe File Move (local-nodes) и образец `nodes/package.json` с `@prokodo/n8n-nodes-pdf-toolkit@0.1.2`; ставятся в том `N8N_DATA_DIR`, не в образ.
- `ollama/` — Modelfile `qwen2.5vl:7b-16k`.
- `helpers/` — check_env (sh/ps1), check_odata, validate_profile, selfcheck.
- `profile/` — шаблон профиля и описание полей; `docs/` — 1С/OData, DaData, установка программ, путь клиента, боевой состав n8n.

## Что получает клиент
Рабочую среду в своём контуре: n8n 2.39.5 (:5678, xlsx через `NODE_FUNCTION_ALLOW_EXTERNAL`, без Execute Command), docreader 0.2.x (:8011), Ollama с моделью, ноды Safe File Move + PDF Toolkit, папки документов, `profile.json` без секретов на диске, отчёт самопроверки. Установку ведёт ассистент вместе с клиентом — это часть продукта.

## Что проверено
- 28.10.2026, Mac Виктории, тестовый стек `~/ai-accountant-test/` (порты 5679/8012): образ n8n собран без npm, docreader health ok, n8n HTTP 200, Ollama и модель доступны. Боевой n8n_1 не трогали.
- box: validate_profile.py (профиль ИВЕНТ), check_odata.py (имитация 1С); 05.11 — сверка compose/.env/Dockerfile со SKILL, чистка `._*`, сборка архива.

## Что НЕ входит
- Сценарии учёта (поступление, Банк-Касса и т.д.) и перенос профиля в workflow «Профиль Организации» — это установщик купленного сценария (следующий контур).
- MCP 1С (1c-mcp-toolkit) — отложено.
- Проверка на Windows — нет машины; `check_env.ps1` и пути Windows не прогонялись.
- Хостинг, офлайн-сборка docreader (`Dockerfile.offline`, wheels), тесты docreader.

## Критерии «готово к упаковке»
- [x] Состав пакета соответствует боевому n8n (2.39.5, xlsx через env, NODES_EXCLUDE, bind-mount N8N_DATA_DIR, ноды в томе).
- [x] В пакете нет секретов, `.env`, AppleDouble `._*`.
- [x] Нет заглушек «_уточнить_»; путь поддержки описан без выдуманных контактов.
- [x] Граница ответственности «среда ↔ сценарий» записана в SKILL и README.
- [x] Сборка и health на Mac пройдены (28.10, тестовый стек).
- [ ] Сквозной прогон SKILL «с нуля» на чистой машине (включая шаг 2.6 нод и selfcheck) — рекомендуется до первого клиента.
- [ ] Windows-verify — отдельно, когда будет машина.
