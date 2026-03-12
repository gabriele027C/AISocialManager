# Storylab.io — AI Social Content Manager

Storylab.io e' un'applicazione Python full-stack che genera automaticamente contenuti per i social media — post con **testo sovrapposto su immagini HD** generate da AI — e li pubblica su **Instagram** (anche come carousel multi-slide) e **Facebook** tramite le API di Meta, previa approvazione manuale.

Include un **bot Telegram** per gestire tutto da remoto e un **frontend web** con anteprima carousel.

---

## Funzionalita'

- **Generazione AI** — Testi con Google Gemini 2.5 Flash, immagini HD con Google Imagen 4.0
- **Temi dinamici** — Seleziona il tema dei contenuti (crescita personale, enoteca, fitness, ristorante...) senza modificare il codice, tramite `themes.json`
- **Text-on-image** — Il testo viene stampato sopra l'immagine con overlay scuro. Se il testo e' lungo viene diviso in piu' slide
- **Carousel Instagram** — Testi lunghi vengono pubblicati come carousel scorrevole (fino a 10 slide)
- **Workflow di approvazione** — Bozza → Approvazione → Scheduling → Pubblicazione
- **Pubblicazione automatica** — I post approvati vengono pubblicati all'orario programmato su Facebook e Instagram
- **Pubblica ora** — Pulsante per pubblicare immediatamente senza programmare
- **Bot Telegram** — Genera, approva, programma e monitora i post direttamente dalla chat
- **Frontend web** — Dashboard, creazione post con selettore tema, anteprima carousel con testo su immagine, storico pubblicazioni
- **Date in formato italiano** — GG/MM/AAAA HH:MM in tutta l'interfaccia

---

## Struttura del progetto

```
AISocialManager/
├── main.py                         # Entrypoint FastAPI
├── config.py                       # Configurazione da .env
├── requirements.txt                # Dipendenze Python
├── themes.json                     # Temi e prompt AI (personalizzabili)
├── .env                            # Variabili d'ambiente (API key, ecc.)
├── db/
│   ├── database.py                 # Setup SQLAlchemy + SQLite
│   └── models.py                   # Modello Post
├── api/
│   ├── routes_posts.py             # API CRUD post, generazione, temi, publish-now
│   └── routes_schedule.py          # API scheduling
├── services/
│   ├── content_generator.py        # Generazione testo (Google Gemini 2.5 Flash)
│   ├── image_generator.py          # Generazione immagini (Google Imagen 4.0)
│   ├── image_composer.py           # Composizione testo su immagine + split in slide
│   ├── meta_publisher.py           # Pubblicazione Facebook + Instagram (carousel)
│   ├── scheduler.py                # Scheduling con APScheduler
│   └── telegram_bot.py             # Bot Telegram
├── generated_images/               # Immagini e slide generate (auto-creata)
└── static/
    └── index.html                  # Frontend SPA
```

---

## Setup

### 1. Prerequisiti

- Python 3.11+
- Una API key [Google AI Studio](https://aistudio.google.com/apikey) (per Gemini e Imagen)
- Un'app registrata su [Meta for Developers](https://developers.facebook.com/)
- Una pagina Facebook collegata a un account Instagram Business
- Un bot Telegram (creato via [@BotFather](https://t.me/BotFather))

### 2. Installazione

```bash
cd AISocialManager
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/macOS
pip install -r requirements.txt
```

### 3. Configurazione

Copia `.env.example` in `.env` e compila tutti i valori:

```bash
cp .env.example .env
```

| Variabile | Dove trovarla |
|---|---|
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/apikey) |
| `META_APP_ID` | Meta for Developers → La tua app → Impostazioni |
| `META_APP_SECRET` | Meta for Developers → La tua app → Impostazioni |
| `META_ACCESS_TOKEN` | Graph API Explorer → Genera token Page con permessi `pages_manage_posts`, `instagram_basic`, `instagram_content_publish` |
| `FACEBOOK_PAGE_ID` | Graph API Explorer → GET /me/accounts → id della pagina |
| `INSTAGRAM_BUSINESS_ACCOUNT_ID` | Graph API Explorer → GET /{page_id}?fields=instagram_business_account → id |
| `TELEGRAM_BOT_TOKEN` | @BotFather su Telegram → /newbot |
| `TELEGRAM_CHAT_ID` | Scrivi al tuo bot, poi visita `https://api.telegram.org/bot<TOKEN>/getUpdates` → result[0].message.chat.id |
| `THEME` | Tema predefinito: `crescita_personale`, `enoteca`, `fitness`, `ristorante` (o un ID custom in `themes.json`) |

### 4. Avvio

```bash
python main.py
```

Il server si avvia su **http://localhost:8000**

---

## Utilizzo

### Frontend Web

1. Apri **http://localhost:8000** nel browser
2. Vai nella sezione **Crea Post**:
   - Seleziona il **tema** dal menu a tendina
   - Scegli quanti post generare e le piattaforme
3. L'AI genera testo e immagine per ogni post
4. Nella sezione **Anteprima**, rivedi ogni post:
   - Il testo appare **sovrapposto all'immagine** con effetto carousel scorrevole
   - Clicca **Pubblica ora** per pubblicare immediatamente
   - Oppure inserisci data/ora (GG/MM/AAAA HH:MM) e clicca **Programma**
   - Puoi **Rigenerare** testo o immagine se non ti convincono
5. I post programmati vengono pubblicati automaticamente all'orario scelto

### Bot Telegram

Apri il tuo bot su Telegram e usa i seguenti comandi:

| Comando | Descrizione |
|---|---|
| `/start` | Mostra i comandi disponibili |
| `/genera N` | Genera N post (default 1, max 10) |
| `/coda` | Mostra i post in bozza con anteprima |
| `/programmati` | Mostra i post programmati |
| `/storico` | Ultimi 10 post pubblicati |
| `/stato` | Stato del server e conteggi |

Ogni post generato arriva con **pulsanti inline** per:
- **Approva** → scegli quando pubblicare (adesso, oggi 18:00, domani 09:00, orario custom)
- **Rigenera testo** / **Rigenera immagine**
- **Elimina**

### Temi personalizzati

I temi sono definiti in `themes.json`. Per aggiungerne uno nuovo, aggiungi un blocco:

```json
{
  "mio_tema": {
    "name": "Il Mio Tema",
    "system_instruction": "Sei un content creator esperto di...",
    "user_prompt": "Genera un post unico per i social media a tema..."
  }
}
```

Il nuovo tema apparira' automaticamente nel selettore del frontend e sara' disponibile via API.

---

## Come funziona la pubblicazione

### Facebook
L'immagine con testo sovrapposto viene caricata direttamente via **multipart upload** — non serve un URL pubblico.

### Instagram
Instagram richiede un URL pubblico per le immagini. Il sistema gestisce tutto automaticamente:

1. Le slide vengono caricate su **Catbox.moe** (gratuito, nessuna API key)
2. Se Catbox non e' disponibile, usa il **Telegram Bot API** come fallback
3. Per testi corti → post singolo con immagine
4. Per testi lunghi → **carousel** multi-slide scorrevole

### Token Meta
Il token di accesso di Meta ha una scadenza. Usa il [Graph API Explorer](https://developers.facebook.com/tools/explorer/) per generare un token a lunga durata (60 giorni) o implementa il flusso di refresh automatico.

---

## Stack tecnologico

| Componente | Tecnologia |
|---|---|
| Backend | Python, FastAPI, uvicorn |
| Database | SQLite, SQLAlchemy |
| Scheduling | APScheduler |
| AI Testo | Google Gemini 2.5 Flash |
| AI Immagini | Google Imagen 4.0 |
| Composizione slide | Pillow (text-on-image) |
| Social API | Meta Graph API v21.0 |
| Image hosting | Catbox.moe / Telegram Bot API |
| Bot | python-telegram-bot |
| Frontend | HTML/CSS/JS vanilla (SPA) |
