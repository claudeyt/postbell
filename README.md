# Postbell Desktop

Aplicativo desktop pra agendamento e upload em massa de vídeos pra canais do YouTube. Electron + Python FastAPI + React, self-contained nessa pasta.

## Estrutura

```
postbellelectron/
├── main.js, preload.js, migration.js    ← Electron main process
├── frontend/                            ← React + Vite source
├── backend/                             ← FastAPI Python source
├── scripts/
│   ├── bundle-backend.py                ← PyInstaller wrapper
│   └── postbell-backend.spec            ← PyInstaller spec
├── electron-builder.json                ← Packaging config + GitHub publish
├── release.bat                          ← UM duplo-clique = nova versão
├── dist/                                ← Installer output (gitignored)
├── dist-renderer/                       ← React bundle (gitignored)
├── dist-backend/                        ← Python bundle (gitignored)
└── ARCHITECTURE.md, POST_MORTEM.md      ← Docs pra contexto
```

Dados runtime do app: `C:\Users\juanh\Desktop\projetos\shared-data\postbell\` (DB, OAuth tokens, settings — não fica nessa pasta).

---

## Como rodar (uso normal)

Instala o `.exe`:
```
dist\Postbell Setup X.Y.Z.exe
```

Atalho do Postbell aparece na área de trabalho. Dois cliques → abre.

---

## Como editar código

Tudo numa pasta só. Mexe direto em:

- **`frontend/src/`** — telas React. Após editar, ele recompila no próximo build.
- **`backend/`** — APIs FastAPI. Após editar, ele recompila no próximo build.
- **`main.js`** / `preload.js` — comportamento do Electron (janela, IPC, spawn do backend).

Testar mudanças sem empacotar:
```powershell
cd C:\Users\juanh\Desktop\projetos\postbellelectron
npm run dev
```

Isso abre Electron + Vite dev server. Hot reload nas mudanças do React.

---

## Como publicar uma nova versão (auto-update)

**Um duplo-clique:**
```
release.bat
```
ou via terminal:
```powershell
.\release.bat patch    # 0.1.0 -> 0.1.1
.\release.bat minor    # 0.1.0 -> 0.2.0
.\release.bat major    # 0.1.0 -> 1.0.0
```

O script faz tudo automático:
1. Bumpa a versão no `package.json`
2. Rebuilda o backend Python (PyInstaller)
3. Rebuilda o frontend React + gera installer NSIS
4. Publica release no GitHub via `gh CLI`

Quem tem o app instalado pega o update automático **na próxima vez que abrir** (esperando 30s após a janela abrir).

---

## Setup do auto-update (uma vez só)

Pré-requisitos pro `release.bat` funcionar:

### 1. Autenticar GitHub CLI

```powershell
gh auth login
```
Escolhe GitHub.com → HTTPS → autenticar via browser. Login com a conta `claudeyt`.

### 2. Criar o repo no GitHub

Vai em https://github.com/new e cria:
- **Repository name**: `postbell`
- **Owner**: `claudeyt`
- Pode ser **público ou privado** — auto-update funciona nos dois (mas privado exige token).
- **NÃO** inicializa com README (vai conflitar com a primeira release).

Já tá configurado em `electron-builder.json`:
```json
"publish": {
  "provider": "github",
  "owner": "claudeyt",
  "repo": "postbell"
}
```

Se quiser mudar nome do repo, troca o `repo` ali.

### 3. Primeira release

Roda `release.bat`. Ele cria a tag `v0.1.1` (próxima patch), faz upload dos 3 arquivos:
- `Postbell Setup 0.1.1.exe`
- `Postbell Setup 0.1.1.exe.blockmap`
- `latest.yml`

A partir daí, todo `release.bat` que você rodar publica uma versão nova e os apps instalados vão atualizar sozinhos.

---

## OAuth Desktop (uma vez por projeto Google)

Pra **adicionar uma nova conta Google** no Postbell, você precisa de um OAuth Client tipo "Aplicativo para computador" no Google Cloud Console:

1. https://console.cloud.google.com/ → seu projeto com YouTube Data API + YouTube Analytics habilitados
2. **APIs e Serviços → Credenciais → + CRIAR CREDENCIAIS → ID do cliente OAuth**
3. **Tipo de aplicativo**: `Aplicativo para computador` (NÃO "Aplicativo da Web")
4. Nome: `Postbell Desktop`
5. Clica **Criar** → baixa o JSON
6. No Postbell: **Settings → Accounts → + Adicionar conta** → aponta pro JSON baixado

Suas 7 contas atuais (Raijins, Manhwa Hollow, SUBARU) **continuam funcionando** sem reauth — os tokens já em `shared-data/postbell/tokens/` têm refresh embedded.

---

## Code signing (opcional)

O installer é **não-assinado**. Windows SmartScreen vai mostrar "publisher unknown" na primeira execução (clica "Mais informações" → "Executar assim mesmo"). Pra eliminar:

- Compra um certificado de code signing (~R$1000/ano, ex: SSL.com, Sectigo)
- Configura `win.certificateFile` e `win.certificatePassword` (ou env vars) em `electron-builder.json`
- Rebuilda

---

## Trabalhando com `shared-data/`

Postbell lê e escreve em `C:\Users\juanh\Desktop\projetos\shared-data\postbell\`. Se quiser fazer backup dos canais/tokens, copia essa pasta. Se quiser **resetar** o app: apaga o `postbell.db` e os tokens, próximo launch fica vazio.

Pra integração com outros apps do `projetos/` (ex: ChannelOrganizer), eles podem ler files dessa pasta diretamente — ver `ARCHITECTURE.md`.

---

## Suporte / docs

- `ARCHITECTURE.md` — design completo do sistema (multi-app vision)
- `POST_MORTEM.md` — bugs encontrados durante a migração + soluções
