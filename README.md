# ⚖️ នីតិ AI — Telegram Legal Router Bot

Telegram bot ជា **អ្នកនាំផ្លូវ (router)** រវាង Google Apps Script ពីរ៖

1. **⚡ សំណួរ–ចម្លើយ ន័យត្រង់** → `GAS_LITERAL_URL` (ឧ. ស្វែងរកខ្លឹមសារពី `.md` files ក្នុង Google Drive)
2. **✦ សំណួរ–ចម្លើយ បែបអធិប្បាយ** → `GAS_EXPLAIN_URL` (ឧ. ប្រើ `Victor.json` និង Google Sheets តាមច្បាប់នីមួយៗ)

Project ប្រើ **Python 3.12 + FastAPI + Telegram Webhook** និងត្រៀមសម្រាប់ GitHub/Render។ Gemini API key គួររក្សានៅក្នុង GAS; Bot បញ្ជូនតែឈ្មោះ model ដែលកំណត់តាម `GEMINI_MODEL`។

## UX ដែលបាន Design

- Premium welcome menu ជាមួយ Inline Keyboard ពីរ Mode
- រក្សា Mode របស់អ្នកប្រើរហូតដល់ពួកគេប្ដូរ
- Processing message និង typing indicator ពេល GAS កំពុងគិត
- បែងចែកចម្លើយវែងដោយស្វ័យប្រវត្តិ ដើម្បីមិនលើស Telegram limit
- ប៊ូតុង «សួរបន្ត», «ប្ដូរ Mode», «ជំនួយ» ក្រោមចម្លើយ
- `/start`, `/menu`, `/mode`, `/help`
- Rate limit ដើម្បីការពារថ្លៃ Gemini និង spam
- Webhook secret validation, queue workers និងការពារ update ស្ទួន
- Health check សម្រាប់ Render

## Architecture

```text
Telegram user
     │
     ▼
Telegram Bot API
     │ webhook
     ▼
FastAPI on Render
     │
     ├── mode=literal ──► GAS #1 ──► Drive .md ──► Gemini
     │
     └── mode=explain ─► GAS #2 ──► Victor.json + Sheets ─► Gemini
```

## 1. ត្រៀម Google Apps Script

GAS ទាំងពីរគួរទទួល `POST` JSON ដែលមាន `question` ហើយត្រឡប់៖

```json
{"ok": true, "answer": "ចម្លើយ..."}
```

សូមមើល contract និង wrapper code លម្អិតនៅ [`docs/GAS_CONTRACT.md`](docs/GAS_CONTRACT.md)។

## 2. បង្កើត Telegram Bot

1. បើក `@BotFather` ក្នុង Telegram។
2. ប្រើ `/newbot` ហើយរក្សា token ទុកដោយសុវត្ថិភាព។
3. Profile image អាចដាក់ logo ពណ៌ navy/gold មានរូបជញ្ជីងច្បាប់ ដើម្បីឱ្យស្រប premium UI។
4. Bot commands និង description ត្រូវបាន project កំណត់ដោយស្វ័យប្រវត្តិពេល startup។

## 3. សាកល្បងក្នុង local

```bash
cp .env.example .env
# កែតម្លៃក្នុង .env
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest -q
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

`GET http://localhost:8000/health` គួរត្រឡប់ `status: ok`។ Telegram webhook ត្រូវការ public HTTPS URL; សម្រាប់ local ត្រូវប្រើ tunnel ឬធ្វើតេស្តពេញលេញលើ Render។

## 4. Push ទៅ GitHub

```bash
git init
git add .
git commit -m "Initial Khmer legal router bot"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
git push -u origin main
```

`.env` ត្រូវបាន ignore រួចហើយ។ **កុំ commit token/API key**។ GitHub Actions នឹងរត់ Ruff និង tests រាល់ពេល push។

## 5. Deploy លើ Render

### វិធី Blueprint (ណែនាំ)

1. នៅ Render ចុច **New → Blueprint**។
2. ភ្ជាប់ GitHub repository នេះ។ Render នឹងអាន `render.yaml`។
3. បញ្ចូល secret variables ដែល Render សួរ៖
   - `TELEGRAM_BOT_TOKEN`
   - `GAS_LITERAL_URL`
   - `GAS_EXPLAIN_URL`
4. `TELEGRAM_WEBHOOK_SECRET` ត្រូវបាន Generate ដោយស្វ័យប្រវត្តិ។
5. Deploy ហើយមើល logs រហូតឃើញ៖

```text
Telegram bot connected: @your_bot
Telegram webhook configured: https://.../telegram/webhook
```

Render ជាធម្មតាផ្ដល់ `RENDER_EXTERNAL_HOSTNAME` ឱ្យ app ដោយស្វ័យប្រវត្តិ។ បើ log សរសេរថា webhook មិនត្រូវបាន configure សូមបន្ថែម៖

```env
PUBLIC_BASE_URL=https://YOUR-SERVICE.onrender.com
```

ហើយ redeploy។

### Optional Render variables

```env
GAS_API_KEY=shared-secret-used-by-both-gas-apps
GAS_LITERAL_RESPONSE_PATH=answer
GAS_EXPLAIN_RESPONSE_PATH=answer
GEMINI_MODEL=gemini-3.5-flash-lite
BOT_BRAND_NAME=នីតិ AI
RATE_LIMIT_QUESTIONS=6
RATE_LIMIT_WINDOW_SECONDS=60
```

ឈ្មោះ model ត្រូវបានកំណត់ជាបរិស្ថាន ដូច្នេះអាចប្ដូរតាម model ID ដែល Google AI Studio/API account របស់អ្នកគាំទ្រ ដោយមិនកែ code។

## GAS Response ផ្សេងពី `{answer: ...}`

បើ GAS ទី២ត្រឡប់៖

```json
{"data":{"result":{"text":"..."}}}
```

កំណត់នៅ Render៖

```env
GAS_EXPLAIN_RESPONSE_PATH=data.result.text
```

Adapter ក៏អាន plain text និង fields ទូទៅមួយចំនួនដោយស្វ័យប្រវត្តិ។

## State និង Database

MVP នេះប្រើ **in-memory state**៖

- Mode នៅជាប់ពេលអ្នកប្រើសួរបន្តក្នុង process ដដែល។
- Mode នឹង reset ពេល Render restart/redeploy/sleep។
- មិនត្រូវការ database និងសន្សំធនធានសម្រាប់ការសាកល្បងដំបូង។

ពេលចង់ production អាចប្ដូរ `MemoryStateStore` ទៅ Render PostgreSQL ដោយរក្សា interface `get_mode`, `set_mode`, `clear_mode` ដដែល។

## Security checklist

- Telegram token, Gemini key និង GAS secret មិនត្រូវដាក់ក្នុង GitHub។
- ប្រើ GAS deployment URL ដែលបញ្ចប់ដោយ `/exec` មិនមែន `/dev`។
- ប្រសិនបើ GAS Web App បើក public សូមប្រើ `GAS_API_KEY` និងពិនិត្យ `apiKey` ក្នុង `doPost`។
- Bot មិន log ខ្លឹមសារសំណួរទេ; វា log តែ IDs, mode និងចំនួនតួអក្សរ។
- កុំបញ្ជូនឯកសារសម្ងាត់ ឬទិន្នន័យផ្ទាល់ខ្លួនដែលមិនចាំបាច់ទៅ model។

## Health endpoint

`GET /health`

```json
{
  "status": "ok",
  "botReady": true,
  "storage": "memory",
  "queueSize": 0,
  "selectedModes": 3
}
```

បើ `botReady` ជា `false` សូមមើល Render logs ជាពិសេស Telegram token និង webhook configuration។
