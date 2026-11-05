# Осмотр компьютера (Windows). Только читает, ничего не ставит и не меняет.
# Запуск: powershell -ExecutionPolicy Bypass -File check_env.ps1
function Say($k,$v){ Write-Output "$k=$v" }
function Ver($cmd,$arg){ if (Get-Command $cmd -ErrorAction SilentlyContinue) { (& $cmd $arg 2>$null | Select-Object -First 1) } else { "нет" } }
$os = Get-CimInstance Win32_OperatingSystem
Say os "$($os.Caption) $($os.Version)"
Say arch $env:PROCESSOR_ARCHITECTURE
Say ram_gb ([math]::Floor($os.TotalVisibleMemorySize/1MB))
Say disk_free_gb ([math]::Floor((Get-PSDrive C).Free/1GB))
$wsl = (wsl.exe --status 2>$null) -join ' '
if ($LASTEXITCODE -eq 0) { Say wsl2 "да" } else { Say wsl2 "нет" }
Say python3 (Ver python --version)
Say node (Ver node --version)
Say docker (Ver docker --version)
if (Get-Command docker -ErrorAction SilentlyContinue) {
  docker info *> $null; if ($LASTEXITCODE -eq 0) { Say docker_running "да" } else { Say docker_running "нет" }
  Say container_n8n (docker ps -a --filter "name=^n8n$" --format "{{.Status}}" 2>$null)
  Say container_docreader (docker ps -a --filter "name=^docreader$" --format "{{.Status}}" 2>$null)
}
Say ollama (Ver ollama --version)
try { Invoke-RestMethod -TimeoutSec 3 http://localhost:11434/api/tags | Out-Null; Say ollama_running "да" } catch { Say ollama_running "нет" }
if (Get-Command ollama -ErrorAction SilentlyContinue) { Say ollama_models ((ollama list | Select-Object -Skip 1 | ForEach-Object { ($_ -split '\s+')[0] }) -join ',') }
foreach ($p in 5678,8011,11434) {
  if (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue) { Say "port_$p" "занят" } else { Say "port_$p" "свободен" }
}
try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 http://localhost:5678/healthz | Out-Null; Say n8n_answers "да" } catch { Say n8n_answers "нет" }
try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 http://localhost:8011/health | Out-Null; Say docreader_answers "да" } catch { Say docreader_answers "нет" }
