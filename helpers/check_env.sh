#!/bin/bash
# Осмотр компьютера (Mac). Только читает, ничего не ставит и не меняет.
# Вывод — строки «ключ=значение», их разбирает скилл.
say(){ printf '%s=%s\n' "$1" "$2"; }
say os "$(sw_vers -productName 2>/dev/null) $(sw_vers -productVersion 2>/dev/null)"
say arch "$(uname -m)"
say ram_gb "$(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824 ))"
say disk_free_gb "$(df -g "$HOME" 2>/dev/null | awk 'NR==2{print $4}')"
v(){ command -v "$1" >/dev/null 2>&1 && "$@" 2>/dev/null | head -1 || echo нет; }
say homebrew "$(v brew --version)"
say python3 "$(v python3 --version)"
say node "$(v node --version)"
say docker "$(v docker --version)"
if command -v docker >/dev/null 2>&1; then
  docker info >/dev/null 2>&1 && say docker_running да || say docker_running нет
  say docker_compose "$(docker compose version 2>/dev/null | head -1 || echo нет)"
  say container_n8n "$(docker ps -a --filter name=^n8n$ --format '{{.Status}}' 2>/dev/null || true)"
  say container_docreader "$(docker ps -a --filter name=^docreader$ --format '{{.Status}}' 2>/dev/null || true)"
fi
say ollama "$(v ollama --version)"
curl -fsS -m 3 http://localhost:11434/api/tags >/dev/null 2>&1 && say ollama_running да || say ollama_running нет
command -v ollama >/dev/null 2>&1 && say ollama_models "$(ollama list 2>/dev/null | awk 'NR>1{print $1}' | paste -sd, -)"
for p in 5678 8011 11434; do
  lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && say port_$p занят || say port_$p свободен
done
curl -fsS -m 3 http://localhost:5678/healthz >/dev/null 2>&1 && say n8n_answers да || say n8n_answers нет
curl -fsS -m 3 http://localhost:8011/health >/dev/null 2>&1 && say docreader_answers да || say docreader_answers нет
