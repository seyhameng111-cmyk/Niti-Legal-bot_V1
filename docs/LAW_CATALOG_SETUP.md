# Dynamic LAW_CATALOG Setup

`LAW_CATALOG` ជាប្រភពកណ្ដាលសម្រាប់ផ្ទាំងដំបូង Telegram។ ការបន្ថែមច្បាប់ថ្មីមិនត្រូវការកែ Python Bot ទេ៖ បន្ថែម row ក្នុង Sheet, កំណត់ `active=TRUE`, រួចចុច «↻ ធ្វើបច្ចុប្បន្នភាព» ក្នុង Bot។

## 1. បង្កើត Sheet tab

ក្នុង Spreadsheet ដែលកំណត់ជា Script Property `SPREADSHEET_ID`៖

1. បង្កើត tab ថ្មីឈ្មោះ `LAW_CATALOG`។
2. Import ឬ copy ពី `templates/LAW_CATALOG_TEMPLATE.csv`។
3. រក្សាឈ្មោះ columns ឱ្យដូចខាងក្រោមទាំងស្រុង៖

| Column | គោលបំណង |
|---|---|
| `law_id` | ID អចិន្ត្រៃយ៍សម្រាប់ Telegram callback; អង់គ្លេស/លេខ/`_`/`-`, អតិបរមា 40 តួ |
| `title_km` | ឈ្មោះច្បាប់ពេញដែលបង្ហាញក្នុងសារ |
| `button_label` | ឈ្មោះខ្លីលើ Inline button |
| `emoji` | Emoji មួយ ឧ. `⚖️`, `📘`, `🏛️` |
| `direct_md_file_id` | Google Drive File ID របស់ `.md` សម្រាប់ Mode ន័យត្រង់ |
| `explain_law_name` | តម្លៃ `law_name` ក្នុង Master Index JSON សម្រាប់ Vector mode |
| `sheet_tab_name` | ឈ្មោះ Google Sheet tab ដែលផ្ទុកមាត្រា/ខ្លឹមសារច្បាប់នោះ |
| `active` | `TRUE` ដើម្បីបង្ហាញ; `FALSE` ដើម្បីលាក់ដោយមិនលុប row |
| `sort_order` | លេខតម្រៀប ឧ. 10, 20, 30 |

## 2. ឧទាហរណ៍ row ដែលបានបំពេញ

```csv
civil_code,ក្រមរដ្ឋប្បវេណី,ក្រមរដ្ឋប្បវេណី,⚖️,1AbCdEfFileId,civil_code,CIVIL_CODE,TRUE,10
```

លក្ខខណ្ឌ៖

- `civil_code` មិនត្រូវប្ដូរ ក្រោយ Bot បានប្រើរួច។
- `explain_law_name=civil_code` ត្រូវផ្គូផ្គង Master Index `law_name` 100%។
- `sheet_tab_name=CIVIL_CODE` ត្រូវផ្គូផ្គងឈ្មោះ tab 100%។
- `direct_md_file_id` គឺ ID ក្នុង URL `https://drive.google.com/file/d/FILE_ID/view`។

## 3. កែ GAS អធិប្បាយ

ប្រើ `gas-explanatory-legal-bot.gs` version ថ្មី។ វាគាំទ្រ៖

```json
{"action":"list_laws"}
```

Response៖

```json
{
  "ok": true,
  "laws": [
    {
      "id": "civil_code",
      "title": "ក្រមរដ្ឋប្បវេណី",
      "buttonLabel": "ក្រមរដ្ឋប្បវេណី",
      "emoji": "⚖️",
      "sortOrder": 10
    }
  ]
}
```

និងសំណួរ៖

```json
{
  "action": "ask",
  "lawId": "civil_code",
  "lawTitle": "ក្រមរដ្ឋប្បវេណី",
  "mode": "explain",
  "question": "..."
}
```

GAS នឹងស្វែងរកតែក្នុង `explain_law_name` ដែល map ទៅ `civil_code`។

## 4. Test ក្នុង Apps Script

រត់តាមលំដាប់៖

1. `testConfiguration_`
2. `testDriveAndIndex_` — បង្ហាញចំនួន LAW_CATALOG rows/active laws
3. `testListLaws_` — ត្រូវបាន JSON មាន `laws`
4. `testMySearch`
5. `testDoPost_`

បន្ទាប់មក Deploy → Manage deployments → Edit → New version → Deploy។

## 5. Python Bot configuration

Bot ប្រើ `GAS_EXPLAIN_URL` ជា catalog endpoint ដោយ default។ មិនចាំបាច់កំណត់ variable ថ្មីទេ។ បើ catalog នៅ GAS ដាច់ដោយឡែក៖

```env
GAS_CATALOG_URL=https://script.google.com/macros/s/.../exec
```

Optional៖

```env
LAW_MENU_PAGE_SIZE=8
LAW_CATALOG_CACHE_SECONDS=300
```

## 6. បន្ថែមច្បាប់ថ្មីនៅពេលក្រោយ

1. Upload `.md` និង copy File ID។
2. បង្កើត/Update Vector JSON និង Master Index entry។
3. បង្កើត Sheet tab និងដាក់ខ្លឹមសារ។
4. បន្ថែម LAW_CATALOG row ដោយប្រើ `law_id` ថ្មី។
5. ពិនិត្យ mapping ទាំងបី។
6. កំណត់ `active=TRUE`។
7. ក្នុង Telegram ចុច «↻ ធ្វើបច្ចុប្បន្នភាព»។

Bot cache បញ្ជីច្បាប់ 5 នាទី ប៉ុន្តែប៊ូតុង Refresh នឹងបង្ខំឱ្យទាញភ្លាម។

## 7. Mode ន័យត្រង់

Python Bot បញ្ជូន `lawId` ទៅ `GAS_LITERAL_URL` រួចហើយ។ GAS ន័យត្រង់ត្រូវយក `lawId` ទៅស្វែងរក `direct_md_file_id` ក្នុង LAW_CATALOG ហើយអានតែ file នោះ។ ដោយសារ GAS ន័យត្រង់ដើមមិនទាន់បានផ្ដល់មក ការភ្ជាប់ function ចុងក្រោយត្រូវធ្វើតាម source code ពិតរបស់វា។
