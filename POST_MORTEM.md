# POST_MORTEM — RESOLVIDO

> Status final: **app funciona**. Duas bugs distintas encontradas e corrigidas.

## TL;DR

1. **Bug real fixado**: `electron-updater@6.8.9` chama `app.getVersion()` no top-level do `require()`. Em Electron 28 e 42, isso crasha porque o singleton `app` ainda não tá inicializado. Fix: lazy-load do `require('electron-updater')` dentro do `setTimeout` (já aplicado em `main.js`).

2. **Falso positivo de packaging**: o motivo do "app não abre janela" durante o debug **era o ambiente de teste**, NÃO o app. O Claude Code (a IA que fez isso) seta `ELECTRON_RUN_AS_NODE=1` no process do shell quando spawna comandos. Esse env var força Electron a rodar como Node puro em vez de Electron main process — `require('electron')` retorna string (path) em vez de objeto API, e a app fecha imediatamente sem mostrar janela.

   Quando o usuário lança o Postbell.exe pelo Explorer/atalho (sem esse env var herdado), tudo funciona normalmente.

## Como confirmei o segundo

```powershell
Remove-Item Env:ELECTRON_RUN_AS_NODE   # limpa só pra essa sessão PS
Start-Process Postbell.exe              # lança herdando env limpo
Start-Sleep 12
Get-Process | Where Name -like "*ostbell*"
```

Resultado: 4 processos Postbell (main + GPU + renderer + network — Electron normal) + 1 postbell-backend (Python). Janela "Postbell" abriu. Dashboard carregou com todos os 7 canais via `shared-data/postbell/`.

## Por que isso me derrubou tanto tempo

- Tipo de falha era silenciosa: `require('electron')` retorna o string path em vez de jogar erro.
- Sem console nativo no packaged exe, não tem feedback visual.
- `Postbell.exe --version` retorna `v18.18.2` (Node 18 do Electron 28) — parece que tá tudo OK.
- Eu testei várias hipóteses (antivírus, asar integrity, electron-builder versão, node_modules corrompido, Electron downgrade) — nenhuma era a real, mas faria sentido pra esse sintoma.
- Encontrei `ELECTRON_RUN_AS_NODE=1` no env quando finalmente fiz `Get-ChildItem env: | Where Name -like "*ELECTRON*"`.

## Pra próxima IA

Se você for fazer Electron packaging dentro do Claude Code agent:

```bash
# Antes de qualquer teste de exe Electron empacotado:
echo $env:ELECTRON_RUN_AS_NODE   # deve estar VAZIO
# Se aparecer 1: Remove-Item Env:ELECTRON_RUN_AS_NODE  ANTES de spawnar Postbell.exe
```

Esse env var afeta TODOS os Electron-based exe (Postbell, qualquer app empacotado com electron-builder, etc.). Foi setado provavelmente pelo Claude Code porque o próprio Claude Code é um app Electron e precisa rodar como Node quando spawna subprocesso.

## Estado dos arquivos hoje

- `main.js`: limpo, com lazy-load de electron-updater documentado em comment no topo. Production-ready.
- `preload.js`, `migration.js`, `electron-builder.json`: defaults.
- `dist/Postbell Setup 0.1.0.exe`: latest installer (148 MB), funciona.
- `dist-backend/postbell-backend.exe`: bundled Python backend (186 MB), funciona.
- `dist-renderer/`: bundled React SPA, funciona.
- `shared-data/postbell/`: dados do usuário preservados.
- `ARCHITECTURE.md`: design doc completo.

## Histórico de debug (resumo)

Tentativas que **não eram a causa raiz**:
- Desabilitar antivírus do Windows
- Mexer em `electronFuses` (onlyLoadAppFromAsar, enableEmbeddedAsarIntegrityValidation)
- `asar: true` vs `asar: false`
- Path do log em diferentes locais (`C:\Users\juanh\`, `%TEMP%`, etc.)
- `require('node:fs')` vs `require('fs')`
- Downgrade Electron 42 → Electron 28 LTS
- Reinstalar node_modules do zero
- Mover binário pra outra pasta (Documents)
- Launch via diferentes mecanismos (PowerShell `&`, `Start-Process`, `cmd /c start /WAIT`)

Tentativas que **eram a causa raiz parcial**:
- Lazy-load do electron-updater (esse era um bug REAL que afetaria usuários finais — mantido)
- Unset `ELECTRON_RUN_AS_NODE` no shell de teste (esse era o falso positivo do debug — não afeta usuários finais)

## Como o usuário deve usar

1. Vai em `C:\Users\juanh\Desktop\projetos\postbellelectron\dist\`
2. Dois cliques em `Postbell Setup 0.1.0.exe`
3. Windows SmartScreen → "Mais informações" → "Executar assim mesmo"
4. Wizard NSIS — instala em ~30s
5. Atalho na área de trabalho criado → dois cliques
6. App abre direto com seus dados (sem dialog de migração — já tá tudo em shared-data)
