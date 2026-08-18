# កិច្ចសន្យាទិន្នន័យរវាង Telegram Bot និង Google Apps Script

Bot មិនចាំបាច់ដឹងថា GAS ទី១អានឯកសារ `.md` ឬ GAS ទី២អាន `Victor.json`/Google Sheets យ៉ាងដូចម្ដេចទេ។ Bot គ្រាន់តែបញ្ជូនសំណួរទៅ Web App URL ត្រឹមត្រូវ ហើយរង់ចាំ `answer`។

## Request ដែល Bot ផ្ញើ

Bot ប្រើ `POST` ជា JSON៖

```json
{
  "question": "តើកិច្ចសន្យាមានសុពលភាពនៅពេលណា?",
  "mode": "literal",
  "model": "gemini-3.5-flash-lite",
  "source": "telegram",
  "apiKey": "optional-shared-secret",
  "telegram": {
    "chatId": 123456,
    "userId": 123456,
    "username": "example",
    "firstName": "Dara",
    "updateId": 999999
  }
}
```

- Endpoint ទី១ទទួល `mode: literal`។
- Endpoint ទី២ទទួល `mode: explain`។
- ឈ្មោះ field `question` អាចប្ដូរតាម `GAS_QUESTION_FIELD`។
- `model` អាចឱ្យ GAS ប្រើ ឬមិនប្រើក៏បាន។ API key របស់ Gemini គួររក្សានៅក្នុង Script Properties របស់ GAS មិនត្រូវបញ្ជូនមក Bot ទេ។

## Response ដែលណែនាំ

```json
{
  "ok": true,
  "answer": "ចម្លើយជាភាសាខ្មែរ..."
}
```

Bot ក៏អាចអាន plain text និង JSON fields ទូទៅដូចជា `response`, `text`, `message`, `result`, `output` និង `data.answer`។ ប្រសិនបើ GAS ទាំងពីរប្រើ path ខុសគ្នា៖

```env
GAS_LITERAL_RESPONSE_PATH=data.answer
GAS_EXPLAIN_RESPONSE_PATH=result.text
```

## Wrapper គំរូសម្រាប់ GAS នីមួយៗ

យក code ខាងក្រោមទៅបញ្ចូលជុំវិញ function ដែលមានស្រាប់។ ប្ដូរ `answerFromExistingSystem_()` ទៅ function ពិតរបស់អ្នក៖

```javascript
function doPost(e) {
  try {
    const input = JSON.parse(e.postData.contents || "{}");
    const expectedKey = PropertiesService.getScriptProperties()
      .getProperty("BOT_SHARED_SECRET");

    if (expectedKey && input.apiKey !== expectedKey) {
      return json_({ ok: false, error: "Unauthorized" });
    }

    const question = String(input.question || "").trim();
    if (!question) {
      return json_({ ok: false, error: "Question is required" });
    }

    // GAS ទី១៖ function នេះអាចស្វែងរកក្នុង .md files។
    // GAS ទី២៖ function នេះអាចប្រើ Victor.json និង Google Sheets។
    const answer = answerFromExistingSystem_(question, {
      model: input.model,
      telegram: input.telegram,
      mode: input.mode
    });

    return json_({ ok: true, answer: String(answer || "") });
  } catch (err) {
    console.error(err && err.stack ? err.stack : err);
    return json_({ ok: false, error: String(err) });
  }
}

function json_(value) {
  return ContentService
    .createTextOutput(JSON.stringify(value))
    .setMimeType(ContentService.MimeType.JSON);
}
```

> ចំណាំ៖ ប្រសិនបើ wrapper ត្រឡប់ `{ok:false,error:"..."}` ជាមួយ HTTP 200 Bot នឹងបង្ហាញជាសារបញ្ហា មិនយក JSON នោះធ្វើជាចម្លើយឡើយ។

## Deploy GAS ជា Web App

1. ក្នុង Apps Script ចុច **Deploy → New deployment**។
2. ជ្រើស **Web app**។
3. Execute as: **Me**។
4. Who has access: ជ្រើស access ដែល Telegram backend អាចហៅបាន។
5. Copy URL ដែលបញ្ចប់ដោយ `/exec` ទៅ `GAS_LITERAL_URL` ឬ `GAS_EXPLAIN_URL`។
6. ប្រសិនបើ endpoint public សូមកំណត់ `BOT_SHARED_SECRET` ក្នុង Script Properties ហើយកំណត់ secret ដូចគ្នានៅ Render ជា `GAS_API_KEY`។

កុំដាក់ Gemini API key, Telegram token ឬ shared secret ក្នុង GitHub។
