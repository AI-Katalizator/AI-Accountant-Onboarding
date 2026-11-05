# Установка программ — подробно (для ассистента)

## Docker Desktop
- Mac: https://www.docker.com/products/docker-desktop/ → «Download for Mac – Apple Silicon» → перетащить в «Программы» → запустить → принять условия.
- Windows: тот же сайт, «Download for Windows – AMD64». Установщик включит WSL2, нужна перезагрузка. Если просит включить виртуализацию в BIOS — это частая проблема; остановиться и предложить помощь разработчика.
- Настройки → General → «Start Docker Desktop when you sign in» = вкл.
- Настройки → Resources → память для Docker не меньше 4 ГБ (модель работает вне Docker).
- Проверка: `docker info` без ошибок.

## Ollama
- https://ollama.com/download → установить. Проверка: http://localhost:11434 отвечает «Ollama is running».
- Модель: `ollama pull qwen2.5vl:7b` и `ollama create qwen2.5vl:7b-16k -f ollama/Modelfile.qwen2.5vl-7b-16k`.
- Docker ходит к Ollama по адресу `host.docker.internal:11434`. На Windows Ollama слушает только localhost — с Docker Desktop это работает; если docreader не видит модель, задать переменную среды OLLAMA_HOST=0.0.0.0 и перезапустить Ollama (с разрешения клиента).

## n8n и docreader
- Папка `~/ai-accountant/` (Windows: `C:\Users\<имя>\ai-accountant\`) = содержимое `docker/` пакета.
- `.env` по образцу `.env.example`. Секретов в `.env` нет.
- `docker compose up -d --build`. Контейнеры перезапускаются сами (`restart: unless-stopped`), когда стартует Docker Desktop.
- Обновление n8n: поменять N8N_VERSION в `.env`, `docker compose up -d --build`. Данные n8n в томе `n8n_data` сохраняются.
