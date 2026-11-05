# Дополнения к n8n для клиента

Кладутся в том данных n8n (`N8N_DATA_DIR` из `.env`, по умолчанию `~/n8n-data` на машине клиента; внутри контейнера это `/home/node/.n8n`), **не** вшиваются npm-ом в образ.

1. `n8n-nodes-ai-accountant-files/` → `~/n8n-data/local-nodes/n8n-nodes-ai-accountant-files/`
2. `nodes-package.product.json` → основа для `~/n8n-data/nodes/package.json` (SafeFileMove + PDF Toolkit).
3. `@prokodo/n8n-nodes-pdf-toolkit@0.1.2` ставится при установке командой `npm install` **в папке** `~/n8n-data/nodes` (на хосте или одноразовым контейнером с volume), не внутрь `/usr/local/lib/node_modules/n8n`.

В compose обязательно:
- `NODE_FUNCTION_ALLOW_EXTERNAL=@e965/xlsx`
- `NODES_EXCLUDE=["n8n-nodes-base.executeCommand"]`

Подробности: `docs/n8n_boevoy_sostav.md`.
