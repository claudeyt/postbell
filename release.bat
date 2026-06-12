@echo off
rem ============================================================
rem  Postbell — Release script
rem  Uso:
rem    release.bat patch    # 0.1.0 -> 0.1.1
rem    release.bat minor    # 0.1.0 -> 0.2.0
rem    release.bat major    # 0.1.0 -> 1.0.0
rem    release.bat          # default: patch
rem
rem  O que faz, automaticamente:
rem    1. Bumpa a versao no package.json
rem    2. Rebuilda o backend Python (PyInstaller, ~1 min)
rem    3. Rebuilda o frontend React + electron-builder (~2 min)
rem    4. Publica release no GitHub (gh CLI)
rem
rem  Pre-requisitos (uma vez so):
rem    - gh auth login (autenticar GitHub CLI)
rem    - Python no PATH com pyinstaller instalado (pip install pyinstaller)
rem ============================================================

setlocal

cd /d "%~dp0"

set "BUMP_TYPE=%1"
if "%BUMP_TYPE%"=="" set "BUMP_TYPE=patch"

echo.
echo === [1/4] Bumping version (%BUMP_TYPE%) ===
call npm version %BUMP_TYPE% --no-git-tag-version
if errorlevel 1 (
  echo FAIL: npm version
  exit /b 1
)

rem Get the new version from package.json
for /f "tokens=2 delims=:," %%a in ('findstr /c:"\"version\":" package.json') do (
  set "RAW_VERSION=%%a"
)
set "NEW_VERSION=%RAW_VERSION:"=%"
set "NEW_VERSION=%NEW_VERSION: =%"

echo New version: %NEW_VERSION%

echo.
echo === [2/4] Rebuilding Python backend (PyInstaller, ~1 min) ===
call npm run build:backend
if errorlevel 1 (
  echo FAIL: build:backend
  exit /b 1
)

echo.
echo === [3/4] Building installer (electron-builder, ~2 min) ===
call npm run dist
if errorlevel 1 (
  echo FAIL: dist
  exit /b 1
)

echo.
echo === [4/4] Publishing GitHub release v%NEW_VERSION% ===
gh release create v%NEW_VERSION% ^
  "dist\Postbell Setup %NEW_VERSION%.exe" ^
  "dist\Postbell Setup %NEW_VERSION%.exe.blockmap" ^
  "dist\latest.yml" ^
  --title "v%NEW_VERSION%" ^
  --notes "Auto-generated release v%NEW_VERSION%"
if errorlevel 1 (
  echo.
  echo gh release falhou. Possiveis causas:
  echo   - gh CLI nao autenticado: rode "gh auth login"
  echo   - Repo nao existe ainda no GitHub: cria em github.com/new (nome: postbell)
  echo   - Sem permissao: confere o owner em electron-builder.json
  echo.
  echo Os arquivos do build estao em dist\, voce pode publicar manualmente.
  exit /b 1
)

echo.
echo ============================================================
echo  RELEASE v%NEW_VERSION% PUBLICADA
echo  Usuarios instalados receberao update automatico em ate 30s
echo  apos abrirem o app na proxima vez.
echo ============================================================

endlocal
