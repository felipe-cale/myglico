@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "DOCKER_DESKTOP_EXE=C:\Program Files\Docker\Docker\Docker Desktop.exe"
set "COMPOSE_SERVICES=db backend frontend"
set "WAIT_SECONDS=120"
set "BACKEND_WAIT_SECONDS=900"
set "BACKEND_URL=http://localhost:8001/health"
set "BACKEND_CONTAINER=myglico-backend"

call :check_docker_cli || exit /b 1
call :check_docker_compose || exit /b 1
call :ensure_docker_running || exit /b 1

echo.
echo Subindo os servicos %COMPOSE_SERVICES%...
docker compose up --build -d %COMPOSE_SERVICES%
if errorlevel 1 (
  echo.
  echo Falha ao subir os containers.
  echo Confira os logs com: docker compose logs -f db backend frontend
  exit /b 1
)

call :wait_for_backend

echo.
echo Ambiente iniciado com sucesso.
echo Frontend: http://localhost:8000
echo Backend:  http://localhost:8001
echo MySQL:    localhost:3307
echo.
echo Para acompanhar logs:
echo docker compose logs -f db backend frontend
exit /b 0

:wait_for_backend
echo.
echo Aguardando o backend responder em %BACKEND_URL%...
for /L %%I in (1,1,%BACKEND_WAIT_SECONDS%) do (
  powershell -NoProfile -Command ^
    "try { $r = Invoke-WebRequest -UseBasicParsing '%BACKEND_URL%' -TimeoutSec 5; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
  if not errorlevel 1 (
    echo Backend respondeu com sucesso.
    exit /b 0
  )

  docker top %BACKEND_CONTAINER% 2>nul | findstr /C:"python scripts/import_uci_diabetes.py" >nul
  if not errorlevel 1 (
    if %%I==1 echo Import do UCI em andamento. Isso pode levar alguns minutos...
    if %%I==60 echo Import do UCI ainda em andamento...
    if %%I==180 echo Import do UCI ainda em andamento...
    if %%I==300 echo Import do UCI ainda em andamento...
    if %%I==600 echo Import do UCI ainda em andamento...
  ) else (
    if %%I==1 echo Backend ainda nao respondeu ao healthcheck. Aguardando...
    if %%I==60 echo Backend ainda nao respondeu ao healthcheck. Aguardando...
    if %%I==180 echo Backend ainda nao respondeu ao healthcheck. Aguardando...
  )

  powershell -NoProfile -Command "Start-Sleep -Seconds 1" >nul
)

echo O backend nao respondeu ao healthcheck em %BACKEND_WAIT_SECONDS% segundos.
echo Verifique os logs com: docker compose logs -f backend
exit /b 1

:check_docker_cli
where docker >nul 2>nul
if errorlevel 1 (
  echo Docker nao foi encontrado no PATH.
  exit /b 1
)
exit /b 0

:check_docker_compose
docker compose version >nul 2>nul
if errorlevel 1 (
  echo Docker Compose nao esta disponivel.
  exit /b 1
)
exit /b 0

:ensure_docker_running
docker info >nul 2>nul
if not errorlevel 1 (
  echo Docker ja esta em execucao.
  exit /b 0
)

echo Docker nao esta respondendo. Tentando iniciar o servico...
sc query com.docker.service | findstr /I "RUNNING" >nul
if errorlevel 1 (
  net start com.docker.service >nul 2>nul
)

docker info >nul 2>nul
if not errorlevel 1 (
  echo Servico Docker iniciado com sucesso.
  exit /b 0
)

if exist "%DOCKER_DESKTOP_EXE%" (
  echo Abrindo Docker Desktop...
  start "" "%DOCKER_DESKTOP_EXE%"
) else (
  echo Docker Desktop.exe nao foi encontrado em:
  echo %DOCKER_DESKTOP_EXE%
  echo Inicie o Docker Desktop manualmente e rode este script novamente.
  exit /b 1
)

echo Aguardando o Docker inicializar...
for /L %%I in (1,1,%WAIT_SECONDS%) do (
  docker info >nul 2>nul
  if not errorlevel 1 (
    echo Docker pronto.
    exit /b 0
  )
  powershell -NoProfile -Command "Start-Sleep -Seconds 1" >nul
)

echo Docker nao ficou pronto em %WAIT_SECONDS% segundos.
echo Verifique se o Docker Desktop terminou de iniciar e tente novamente.
exit /b 1
