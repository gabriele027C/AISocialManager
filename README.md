# Storylab.io — AI Social Content Manager

Storylab.io è un'applicazione Python full-stack che genera automaticamente contenuti di **crescita personale e spirituale** — post con immagini HD generate da AI — e li pubblica su **Instagram** e **Facebook** tramite le API di Meta, previa approvazione manuale.

Include un **bot Telegram** per gestire tutto da remoto.

---

## Funzionalità

- **Generazione AI** — Testi motivazionali con GPT-4o e immagini HD con DALL·E 3
- **Workflow di approvazione** — Ogni post passa per: Bozza → Approvazione → Scheduling → Pubblicazione
- **Pubblicazione automatica** — I post approvati vengono pubblicati all'orario programmato su Facebook e Instagram
- **Bot Telegram** — Genera, approva, programma e monitora i post direttamente da Telegram
- **Frontend web** — Dashboard, creazione post, anteprima con approvazione e storico pubblicazioni

---

## Struttura del progetto

```
AISocialManager/
├── main.py                     # Entrypoint FastAPI
├── config.py                   # Configurazione da .env
├── requirements.txt            # Dipendenze Python
├── .env                        # Template variabili d'ambiente
├── db/
│   ├── database.py             # Setup SQLAlchemy + SQLite
│   └── models.py               # Modello Post
├── api/
│   ├── routes_posts.py         # API CRUD post + generazione
│   └── routes_schedule.py      # API scheduling
├── services/
│   ├── content_generator.py    # Generazione testo (GPT-4o)
│   ├── image_generator.py      # Generazione immagini (DALL·E 3)
│   ├── meta_publisher.py       # Pubblicazione Facebook + Instagram
│   ├── scheduler.py            # Scheduling con APScheduler
│   └── telegram_bot.py         # Bot Telegram
├── generated_images/           # Immagini generate (auto-creata)
└── static/
    └── index.html              # Frontend SPA
```

---

## Setup

### 1. Prerequisiti

- Python 3.11+
- Un account [OpenAI](https://platform.openai.com/) con API key
- Un'app registrata su [Meta for Developers](https://developers.facebook.com/)
- Una pagina Facebook collegata a un account Instagram Business
- Un bot Telegram (creato via [@BotFather](https://t.me/BotFather))

### 2. Installazione

```bash
cd AISocialManager
pip install -r requirements.txt
```

### 3. Configurazione

Copia il file di esempio e inserisci le tue credenziali:

```bash
cp .env.example .env
```

Apri `.env` e compila tutti i valori:

| Variabile | Dove trovarla |
|---|---|
| `OPENAI_API_KEY` | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `META_APP_ID` | Meta for Developers → La tua app → Impostazioni |
| `META_APP_SECRET` | Meta for Developers → La tua app → Impostazioni |
| `META_ACCESS_TOKEN` | Graph API Explorer → Genera token Page con permessi `pages_manage_posts`, `instagram_basic`, `instagram_content_publish` |
| `FACEBOOK_PAGE_ID` | Graph API Explorer → GET /me/accounts → id della pagina |
| `INSTAGRAM_BUSINESS_ACCOUNT_ID` | Graph API Explorer → GET /{page_id}?fields=instagram_business_account → id |
| `TELEGRAM_BOT_TOKEN` | @BotFather su Telegram → /newbot |
| `TELEGRAM_CHAT_ID` | Scrivi al tuo bot, poi visita `https://api.telegram.org/bot<TOKEN>/getUpdates` → result[0].message.chat.id |

### 4. Avvio

```bash
python main.py
```

Il server si avvia su **http://localhost:8000**

---

## Utilizzo

### Frontend Web

1. Apri **http://localhost:8000** nel browser
2. Vai nella sezione **Crea Post** e scegli quanti post generare
3. L'AI genera testo e immagine per ogni post
4. Nella sezione **Anteprima**, rivedi ogni post:
   - Scegli data/ora di pubblicazione
   - Clicca **Approva e Programma** per confermare
   - Oppure **Rigenera** testo o immagine se non ti convince
5. I post programmati vengono pubblicati automaticamente all'orario scelto

### Bot Telegram

Apri il tuo bot su Telegram e usa i seguenti comandi:

| Comando | Descrizione |
|---|---|
| `/start` | Mostra i comandi disponibili |
| `/genera N` | Genera N post (default 1, max 10) |
| `/coda` | Mostra i post in bozza |
| `/programmati` | Mostra i post programmati |
| `/storico` | Ultimi 10 post pubblicati |
| `/stato` | Stato del server |

Ogni post generato arriva con **pulsanti inline** per approvare, rigenerare o eliminare direttamente dalla chat.

---

## Note importanti

### Instagram e URL pubblici
Instagram richiede che le immagini siano accessibili da un URL pubblico. In ambiente locale, le immagini servite su `localhost` non sono raggiungibili dai server di Meta. Soluzioni:

- **ngrok**: `ngrok http 8000` → usa l'URL HTTPS generato come `BASE_URL` nel `.env`
- **Deploy su server**: Usa un VPS o un servizio cloud con IP pubblico

### Token Meta
Il token di accesso di Meta ha una scadenza. Usa il [Graph API Explorer](https://developers.facebook.com/tools/explorer/) per generare un token a lunga durata (60 giorni) o implementa il flusso di refresh automatico.

---

## Stack tecnologico

| Componente | Tecnologia |
|---|---|
| Backend | Python, FastAPI |
| Database | SQLite, SQLAlchemy |
| Scheduling | APScheduler |
| AI Testo | OpenAI GPT-4o |
| AI Immagini | OpenAI DALL·E 3 |
| Social API | Meta Graph API v21.0 |
| Bot | python-telegram-bot |
| Frontend | HTML/CSS/JS vanilla |
