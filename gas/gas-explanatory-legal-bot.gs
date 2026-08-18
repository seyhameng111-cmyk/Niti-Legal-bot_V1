/**
 * NITI AI - Explanatory Legal Answer Google Apps Script Web App
 *
 * Data flow:
 * Telegram Bot -> doPost -> Gemini router -> Drive vector JSON
 * -> Google Sheets legal content -> Gemini final answer -> JSON {ok, answer}
 *
 * Required Script Properties:
 *   GEMINI_API_KEY
 *   MASTER_INDEX_ID
 *   SPREADSHEET_ID
 *
 * Optional Script Properties:
 *   BOT_SHARED_SECRET
 *   GEMINI_CHAT_MODEL             (default: gemini-3.5-flash-lite)
 *   GEMINI_EMBEDDING_MODEL        (default: gemini-embedding-001)
 *   MAX_SELECTED_LAWS             (default: 3)
 *   TOP_K_PER_VECTOR_FILE         (default: 5)
 *   TOP_ARTICLES_PER_LAW          (default: 8)
 *   MAX_CONTEXT_CHARS             (default: 60000)
 *   MAX_OUTPUT_TOKENS             (default: 4096)
 *   LAW_CATALOG_SHEET             (default: LAW_CATALOG)
 */

var DEFAULT_CONFIG_ = {
  chatModel: "gemini-3.5-flash-lite",
  embeddingModel: "gemini-embedding-001",
  maxSelectedLaws: 3,
  topKPerVectorFile: 5,
  topArticlesPerLaw: 8,
  maxContextChars: 60000,
  maxOutputTokens: 4096,
  lawCatalogSheet: "LAW_CATALOG"
};


// ============================================================
// 1. WEB APP ENTRY POINTS
// ============================================================

/**
 * Simple health endpoint. Opening the /exec URL in a browser calls doGet.
 */
function doGet() {
  return jsonResponse_({
    ok: true,
    service: "NITI explanatory legal GAS",
    status: "online",
    timestamp: new Date().toISOString()
  });
}

/**
 * Receives JSON from the Telegram router bot.
 * Expected request:
 * {
 *   "question": "...",
 *   "mode": "explain",
 *   "model": "gemini-3.5-flash-lite",
 *   "apiKey": "optional shared secret",
 *   "telegram": {...}
 * }
 */
function doPost(e) {
  var startedAt = Date.now();

  try {
    if (!e || !e.postData || !e.postData.contents) {
      throw new Error("POST request body is missing");
    }

    var input;
    try {
      input = JSON.parse(e.postData.contents);
    } catch (parseError) {
      throw new Error("Request body is not valid JSON: " + parseError.message);
    }

    var config = getConfig_();
    verifySharedSecret_(input, config);

    var action = String(input.action || "ask").trim().toLowerCase();

    // Dynamic Telegram first screen: return active laws from LAW_CATALOG.
    if (action === "list_laws") {
      var catalogSpreadsheet = getSpreadsheet_(config);
      var publicLaws = getPublicLawCatalog_(catalogSpreadsheet, config);

      return jsonResponse_({
        ok: true,
        laws: publicLaws,
        count: publicLaws.length,
        timestamp: new Date().toISOString()
      });
    }

    if (action !== "ask") {
      throw new Error("Unsupported action: " + action);
    }

    var question = String(input.question || "").trim();
    if (!question) {
      throw new Error("Question is required");
    }

    // Allow the bot to choose a model, but only if a non-empty value is sent.
    if (input.model && String(input.model).trim()) {
      config.chatModel = normalizeModelName_(String(input.model).trim());
    }

    var result = answerFromExistingSystem_(question, input, config);

    return jsonResponse_({
      ok: true,
      answer: result.answer,
      mode: input.mode || "explain",
      selectedLaws: result.selectedLawIds,
      contextCharacters: result.contextCharacters,
      elapsedMs: Date.now() - startedAt
    });

  } catch (error) {
    var message = getErrorMessage_(error);
    console.error("doPost failed: " + message);
    if (error && error.stack) {
      console.error(error.stack);
    }

    return jsonResponse_({
      ok: false,
      error: message,
      elapsedMs: Date.now() - startedAt
    });
  }
}


// ============================================================
// 2. MAIN LEGAL ANSWER PIPELINE
// ============================================================

/**
 * Runs the complete legal search pipeline and RETURNS the final answer.
 */
function answerFromExistingSystem_(userQuery, options, suppliedConfig) {
  var config = suppliedConfig || getConfig_();
  options = options || {};

  userQuery = String(userQuery || "").trim();
  if (!userQuery) {
    throw new Error("Question cannot be empty");
  }

  console.log("[1/6] Loading master index");
  var masterIndex = readJsonDriveFile_(
    config.masterIndexId,
    "Master Index"
  );

  if (!Array.isArray(masterIndex) || masterIndex.length === 0) {
    throw new Error("Master Index must be a non-empty JSON array");
  }

  validateMasterIndex_(masterIndex);

  var spreadsheet = getSpreadsheet_(config);
  var requestedLawId = String(options.lawId || "").trim();
  var selectedCatalogLaw = null;
  var selectedLawIds = [];

  if (requestedLawId) {
    console.log("[2/6] Applying user-selected law: " + requestedLawId);
    selectedCatalogLaw = findActiveCatalogLawById_(
      spreadsheet,
      config,
      requestedLawId
    );

    if (!selectedCatalogLaw) {
      throw new Error(
        "Selected law_id is missing or inactive in LAW_CATALOG: " +
        requestedLawId
      );
    }

    if (!selectedCatalogLaw.explainLawName) {
      throw new Error(
        "LAW_CATALOG row " + requestedLawId +
        " has no explain_law_name"
      );
    }

    // Strict mode: search only the law selected by the Telegram user.
    selectedLawIds = [selectedCatalogLaw.explainLawName];
  } else {
    // Backwards-compatible fallback used by diagnostics without a selected law.
    console.log("[2/6] Selecting relevant laws with Gemini router");
    selectedLawIds = getMultiSmartRoute_(
      userQuery,
      masterIndex,
      config
    );

    selectedLawIds = uniqueStrings_(selectedLawIds)
      .slice(0, config.maxSelectedLaws);
  }

  if (selectedLawIds.length === 0) {
    throw new Error("No valid law IDs were selected");
  }

  console.log("Selected laws: " + selectedLawIds.join(", "));

  console.log("[3/6] Creating query embedding");
  var queryVector = getGeminiEmbedding_(userQuery, config);

  if (!Array.isArray(queryVector) || queryVector.length === 0) {
    throw new Error("Gemini returned an empty query embedding");
  }

  console.log("Embedding dimensions: " + queryVector.length);

  console.log("[4/6] Searching vectors and reading Google Sheets");
  var contextBlocks = [];
  var contextCharacters = 0;
  var actuallyUsedLawIds = [];

  for (var lawIndex = 0; lawIndex < selectedLawIds.length; lawIndex++) {
    if (contextCharacters >= config.maxContextChars) {
      break;
    }

    var selectedId = selectedLawIds[lawIndex];
    var lawInfo = findLawInfo_(masterIndex, selectedId);

    if (!lawInfo) {
      console.warn("Law ID not found in master index: " + selectedId);
      continue;
    }

    var lawTitle = String(lawInfo.law_title || lawInfo.law_name || selectedId);
    console.log("Searching: " + lawTitle);

    var fileIds = Array.isArray(lawInfo.file_id)
      ? lawInfo.file_id
      : [lawInfo.file_id];

    var allCandidates = [];

    for (var fileIndex = 0; fileIndex < fileIds.length; fileIndex++) {
      var vectorFileId = String(fileIds[fileIndex] || "").trim();
      if (!vectorFileId) {
        continue;
      }

      var partVectors = readJsonDriveFile_(
        vectorFileId,
        "Vector file for " + lawTitle
      );

      if (!Array.isArray(partVectors)) {
        throw new Error("Vector file for " + lawTitle + " must be a JSON array");
      }

      var matches = findBestMatchWithScores_(
        queryVector,
        partVectors,
        config.topKPerVectorFile,
        lawTitle
      );

      allCandidates = allCandidates.concat(matches);
    }

    allCandidates.sort(function(a, b) {
      return b.score - a.score;
    });

    var articleIds = [];
    var seenArticleIds = {};

    for (
      var candidateIndex = 0;
      candidateIndex < allCandidates.length &&
      articleIds.length < config.topArticlesPerLaw;
      candidateIndex++
    ) {
      var articleId = allCandidates[candidateIndex].item.id;
      var normalizedArticleId = String(articleId || "").trim();

      if (normalizedArticleId && !seenArticleIds[normalizedArticleId]) {
        seenArticleIds[normalizedArticleId] = true;
        articleIds.push(normalizedArticleId);
      }
    }

    if (articleIds.length === 0) {
      console.warn("No matching article IDs found for: " + lawTitle);
      continue;
    }

    var sheetTabName = String(lawInfo.law_name || "").trim();
    if (
      selectedCatalogLaw &&
      selectedId === selectedCatalogLaw.explainLawName &&
      selectedCatalogLaw.sheetTabName
    ) {
      sheetTabName = selectedCatalogLaw.sheetTabName;
    }

    var content = getMultipleArticlesFromSheet_(
      spreadsheet,
      sheetTabName,
      articleIds
    );

    if (!content || content.trim().length < 10) {
      console.warn("No Sheet content found for: " + lawTitle);
      continue;
    }

    var contextBlock =
      "\n<<< ខ្លឹមសារពី៖ " + lawTitle + " >>>\n" +
      content.trim() +
      "\n";

    var remainingCharacters = config.maxContextChars - contextCharacters;
    if (contextBlock.length > remainingCharacters) {
      contextBlock = contextBlock.substring(0, remainingCharacters);
    }

    if (contextBlock.trim()) {
      contextBlocks.push(contextBlock);
      contextCharacters += contextBlock.length;
      actuallyUsedLawIds.push(String(lawInfo.law_name || selectedId));
    }
  }

  var fullContext = contextBlocks.join("\n").trim();

  if (fullContext.length < 20) {
    throw new Error(
      "No relevant legal content was found in Google Sheets. " +
      "Check law_name, Sheet tab names, article IDs, and vector dimensions."
    );
  }

  console.log("Context characters: " + fullContext.length);

  console.log("[5/6] Generating final explanatory answer");
  var aiAnswer = askGemini_(userQuery, fullContext, config);

  aiAnswer = String(aiAnswer || "").trim();
  if (!aiAnswer) {
    throw new Error("Gemini returned an empty final answer");
  }

  console.log("[6/6] Answer generated successfully");

  return {
    answer: aiAnswer,
    selectedLawIds: actuallyUsedLawIds.length
      ? actuallyUsedLawIds
      : selectedLawIds,
    contextCharacters: fullContext.length
  };
}


// ============================================================
// 3. GEMINI ROUTER, EMBEDDING, AND FINAL ANSWER
// ============================================================

/**
 * Uses Gemini to choose relevant law_name IDs from the master index.
 */
function getMultiSmartRoute_(query, masterIndex, config) {
  var lawList = masterIndex.map(function(law, index) {
    return (
      (index + 1) +
      ". ID: " + String(law.law_name || "") +
      " | ឈ្មោះ៖ " + String(law.law_title || law.law_name || "")
    );
  }).join("\n");

  var prompt =
    "ជ្រើសរើស ID នៃឯកសារច្បាប់ទាំងអស់ដែលពាក់ព័ន្ធនឹងសំណួរ។\n" +
    "ប្រើតែ ID ដែលមានក្នុងបញ្ជី។\n" +
    "ឆ្លើយតែ ID ប៉ុណ្ណោះ និងបំបែកដោយសញ្ញាក្បៀស។\n" +
    "កុំបន្ថែមសេចក្តីពន្យល់ ឬ Markdown។\n\n" +
    "សំណួរ៖ \"" + query + "\"\n\n" +
    "បញ្ជីឯកសារ៖\n" + lawList;

  var payload = {
    contents: [
      {
        parts: [
          { text: prompt }
        ]
      }
    ],
    generationConfig: {
      temperature: 0,
      maxOutputTokens: 512
    }
  };

  var rawAnswer = callGeminiGenerateText_(
    config.chatModel,
    payload,
    config,
    "Gemini legal router"
  );

  return parseAndValidateLawIds_(rawAnswer, masterIndex);
}

/**
 * Creates an embedding for the user's question.
 */
function getGeminiEmbedding_(text, config) {
  var model = normalizeModelName_(config.embeddingModel);
  var url =
    "https://generativelanguage.googleapis.com/v1beta/models/" +
    encodeURIComponent(model) +
    ":embedContent?key=" +
    encodeURIComponent(config.geminiApiKey);

  var payload = {
    content: {
      parts: [
        { text: String(text) }
      ]
    }
  };

  var json = fetchGeminiJson_(
    url,
    payload,
    "Gemini embedding"
  );

  var values = null;

  if (
    json.embedding &&
    Array.isArray(json.embedding.values)
  ) {
    values = json.embedding.values;
  } else if (
    Array.isArray(json.embeddings) &&
    json.embeddings[0] &&
    Array.isArray(json.embeddings[0].values)
  ) {
    values = json.embeddings[0].values;
  }

  if (!Array.isArray(values) || values.length === 0) {
    throw new Error("Gemini embedding response does not contain embedding.values");
  }

  return values;
}

/**
 * Produces the final long-form Khmer legal explanation.
 */
function askGemini_(query, context, config) {
  var prompt =
    "អ្នកគឺជាមេធាវី និងជាសាស្ត្រាចារ្យច្បាប់ដ៏ជំនាញនៅកម្ពុជា។ " +
    "ភារកិច្ចរបស់អ្នកគឺពន្យល់សំណួរខាងក្រោមឱ្យបានលម្អិត ក្បោះក្បាយ " +
    "និងផ្អែកតែលើប្រភពដែលបានផ្តល់ឱ្យ។\n\n" +

    "ប្រភពខ្លឹមសារ៖\n" +
    context +
    "\n\n" +

    "សំណួរ៖ \"" + query + "\"\n\n" +

    "សេចក្តីណែនាំសម្រាប់ការឆ្លើយ៖\n" +
    "១. រៀបរាប់ឱ្យបានលម្អិត និងមានរចនាសម្ព័ន្ធច្បាស់លាស់។\n" +
    "២. ផ្នែកទី ១៖ អត្ថបទច្បាប់ដើម — ដកស្រង់មាត្រាពាក់ព័ន្ធដែលមានក្នុងប្រភព។\n" +
    "៣. ផ្នែកទី ២៖ ការបកស្រាយលម្អិត — បកស្រាយតាមចំណុចៗដោយផ្អែកលើប្រភព។\n" +
    "៤. ផ្នែកទី ៣៖ ឧទាហរណ៍ជាក់ស្តែង — ប្រើតែឧទាហរណ៍ដែលមានក្នុងប្រភព។\n" +
    "៥. ប្រសិនបើប្រភពមិនគ្រប់គ្រាន់ ត្រូវនិយាយច្បាស់ថាមិនមានព័ត៌មានគ្រប់គ្រាន់។\n" +
    "៦. កុំបង្កើតលេខមាត្រា ខ្លឹមសារច្បាប់ ឬឧទាហរណ៍ដែលមិនមានក្នុងប្រភព។\n" +
    "៧. ប្រើភាសាខ្មែរផ្លូវការ។";

  var payload = {
    contents: [
      {
        parts: [
          { text: prompt }
        ]
      }
    ],
    generationConfig: {
      temperature: 0.2,
      maxOutputTokens: config.maxOutputTokens
    }
  };

  return callGeminiGenerateText_(
    config.chatModel,
    payload,
    config,
    "Gemini final answer"
  );
}

/**
 * Calls generateContent and extracts all text parts.
 */
function callGeminiGenerateText_(modelName, payload, config, label) {
  var model = normalizeModelName_(modelName);
  var url =
    "https://generativelanguage.googleapis.com/v1beta/models/" +
    encodeURIComponent(model) +
    ":generateContent?key=" +
    encodeURIComponent(config.geminiApiKey);

  var json = fetchGeminiJson_(url, payload, label);

  if (!Array.isArray(json.candidates) || !json.candidates[0]) {
    var blockReason =
      json.promptFeedback && json.promptFeedback.blockReason
        ? " Block reason: " + json.promptFeedback.blockReason
        : "";
    throw new Error(label + " returned no candidates." + blockReason);
  }

  var content = json.candidates[0].content;
  var parts = content && Array.isArray(content.parts)
    ? content.parts
    : [];

  var texts = parts.map(function(part) {
    return part && part.text ? String(part.text) : "";
  }).filter(function(text) {
    return text.trim().length > 0;
  });

  var output = texts.join("\n").trim();
  if (!output) {
    throw new Error(label + " returned a candidate without text");
  }

  return output;
}

/**
 * Calls Gemini with retries and returns parsed JSON.
 */
function fetchGeminiJson_(url, payload, label) {
  var lastError = null;

  for (var attempt = 1; attempt <= 3; attempt++) {
    try {
      var response = UrlFetchApp.fetch(url, {
        method: "post",
        contentType: "application/json",
        payload: JSON.stringify(payload),
        muteHttpExceptions: true
      });

      var status = response.getResponseCode();
      var body = response.getContentText();
      var parsed = null;

      try {
        parsed = JSON.parse(body);
      } catch (parseError) {
        if (status >= 200 && status < 300) {
          throw new Error(label + " returned invalid JSON");
        }
      }

      if (status >= 200 && status < 300) {
        return parsed;
      }

      var apiMessage =
        parsed && parsed.error && parsed.error.message
          ? String(parsed.error.message)
          : String(body || "Unknown API error").substring(0, 500);

      lastError = new Error(
        label + " HTTP " + status + ": " + apiMessage
      );

      if (status === 429 || status >= 500) {
        if (attempt < 3) {
          Utilities.sleep(attempt * 1000);
          continue;
        }
      }

      throw lastError;

    } catch (error) {
      lastError = error;

      if (attempt < 3 && isRetryableError_(error)) {
        Utilities.sleep(attempt * 1000);
        continue;
      }

      throw error;
    }
  }

  throw lastError || new Error(label + " failed");
}


// ============================================================
// 4. VECTOR SEARCH
// ============================================================

function findBestMatchWithScores_(queryVector, dataList, topK, label) {
  if (!Array.isArray(dataList)) {
    throw new Error("Vector data for " + label + " must be an array");
  }

  var results = [];
  var firstStoredDimension = null;
  var validVectorCount = 0;

  for (var index = 0; index < dataList.length; index++) {
    var item = dataList[index];
    if (!item || typeof item !== "object") {
      continue;
    }

    var vector = null;

    if (Array.isArray(item.v)) {
      vector = item.v;
    } else if (Array.isArray(item.vector)) {
      vector = item.vector;
    } else if (Array.isArray(item.embedding)) {
      vector = item.embedding;
    }

    if (!Array.isArray(vector) || vector.length === 0) {
      continue;
    }

    if (firstStoredDimension === null) {
      firstStoredDimension = vector.length;
    }

    if (queryVector.length !== vector.length) {
      continue;
    }

    validVectorCount++;
    var score = cosineSimilarity_(queryVector, vector);

    if (isFinite(score)) {
      results.push({
        item: item,
        score: score
      });
    }
  }

  if (
    validVectorCount === 0 &&
    firstStoredDimension !== null &&
    queryVector.length !== firstStoredDimension
  ) {
    throw new Error(
      "Embedding dimension mismatch for " + label +
      ". Query vector has " + queryVector.length +
      " dimensions but stored vectors have " + firstStoredDimension +
      ". Rebuild vectors with model " + getConfig_().embeddingModel + "."
    );
  }

  results.sort(function(a, b) {
    return b.score - a.score;
  });

  return results.slice(0, topK);
}

function cosineSimilarity_(vectorA, vectorB) {
  if (
    !Array.isArray(vectorA) ||
    !Array.isArray(vectorB) ||
    vectorA.length !== vectorB.length ||
    vectorA.length === 0
  ) {
    return NaN;
  }

  var dotProduct = 0;
  var magnitudeA = 0;
  var magnitudeB = 0;

  for (var index = 0; index < vectorA.length; index++) {
    var a = Number(vectorA[index]);
    var b = Number(vectorB[index]);

    if (!isFinite(a) || !isFinite(b)) {
      return NaN;
    }

    dotProduct += a * b;
    magnitudeA += a * a;
    magnitudeB += b * b;
  }

  if (magnitudeA === 0 || magnitudeB === 0) {
    return NaN;
  }

  return dotProduct / (Math.sqrt(magnitudeA) * Math.sqrt(magnitudeB));
}


// ============================================================
// 5. GOOGLE DRIVE AND SHEETS
// ============================================================

function readJsonDriveFile_(fileId, label) {
  fileId = String(fileId || "").trim();
  if (!fileId) {
    throw new Error(label + " file ID is empty");
  }

  try {
    var file = DriveApp.getFileById(fileId);
    var text = file.getBlob().getDataAsString("UTF-8");

    if (!text || !text.trim()) {
      throw new Error(label + " is empty");
    }

    return safeJsonParse_(text, label);

  } catch (error) {
    throw new Error(
      "Cannot read " + label + " from Google Drive: " +
      getErrorMessage_(error)
    );
  }
}

function getSpreadsheet_(config) {
  if (config.spreadsheetId) {
    try {
      return SpreadsheetApp.openById(config.spreadsheetId);
    } catch (error) {
      throw new Error(
        "Cannot open SPREADSHEET_ID: " + getErrorMessage_(error)
      );
    }
  }

  var activeSpreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  if (!activeSpreadsheet) {
    throw new Error(
      "SPREADSHEET_ID is not configured and no active spreadsheet is available"
    );
  }

  return activeSpreadsheet;
}

function getMultipleArticlesFromSheet_(spreadsheet, sheetName, articleIds) {
  sheetName = String(sheetName || "").trim();
  if (!sheetName) {
    throw new Error("law_name is empty; it must match a Sheet tab name");
  }

  var sheet = spreadsheet.getSheetByName(sheetName);
  if (!sheet) {
    console.warn("Sheet tab not found: " + sheetName);
    return "";
  }

  var data = sheet.getDataRange().getDisplayValues();
  if (!Array.isArray(data) || data.length === 0) {
    return "";
  }

  var articleMap = {};

  for (var rowIndex = 0; rowIndex < data.length; rowIndex++) {
    var row = data[rowIndex];
    var rowId = row && row[0] !== undefined
      ? String(row[0]).trim()
      : "";

    var rowContent = row && row[1] !== undefined
      ? String(row[1]).trim()
      : "";

    if (rowId && rowContent && articleMap[rowId] === undefined) {
      articleMap[rowId] = rowContent;
    }
  }

  var contextParts = [];

  for (var idIndex = 0; idIndex < articleIds.length; idIndex++) {
    var requestedId = String(articleIds[idIndex] || "").trim();
    if (requestedId && articleMap[requestedId]) {
      contextParts.push("- " + articleMap[requestedId]);
    }
  }

  return contextParts.join("\n\n");
}


// ============================================================
// 6. DYNAMIC LAW CATALOG
// ============================================================

/**
 * LAW_CATALOG columns:
 * law_id | title_km | button_label | emoji | direct_md_file_id |
 * explain_law_name | sheet_tab_name | active | sort_order
 */
function getLawCatalog_(spreadsheet, config) {
  var sheet = spreadsheet.getSheetByName(config.lawCatalogSheet);
  if (!sheet) {
    throw new Error(
      "LAW_CATALOG Sheet tab not found: " + config.lawCatalogSheet
    );
  }

  var values = sheet.getDataRange().getDisplayValues();
  if (!Array.isArray(values) || values.length < 2) {
    return [];
  }

  var headers = values[0].map(function(value) {
    return String(value || "").trim().toLowerCase();
  });

  var requiredHeaders = [
    "law_id",
    "title_km",
    "button_label",
    "emoji",
    "direct_md_file_id",
    "explain_law_name",
    "sheet_tab_name",
    "active",
    "sort_order"
  ];

  var headerIndex = {};
  for (var headerPosition = 0; headerPosition < headers.length; headerPosition++) {
    if (headers[headerPosition]) {
      headerIndex[headers[headerPosition]] = headerPosition;
    }
  }

  for (var requiredIndex = 0; requiredIndex < requiredHeaders.length; requiredIndex++) {
    var requiredHeader = requiredHeaders[requiredIndex];
    if (headerIndex[requiredHeader] === undefined) {
      throw new Error(
        "LAW_CATALOG is missing column: " + requiredHeader
      );
    }
  }

  var laws = [];
  var seenIds = {};

  for (var rowIndex = 1; rowIndex < values.length; rowIndex++) {
    var row = values[rowIndex];
    var lawId = catalogCell_(row, headerIndex, "law_id");

    // Empty rows are ignored.
    if (!lawId) {
      continue;
    }

    if (!/^[A-Za-z0-9_-]{1,40}$/.test(lawId)) {
      throw new Error(
        "LAW_CATALOG row " + (rowIndex + 1) +
        " has invalid law_id: " + lawId
      );
    }

    if (seenIds[lawId]) {
      throw new Error("LAW_CATALOG contains duplicate law_id: " + lawId);
    }
    seenIds[lawId] = true;

    var title = catalogCell_(row, headerIndex, "title_km");
    if (!title) {
      throw new Error(
        "LAW_CATALOG row " + (rowIndex + 1) +
        " has no title_km"
      );
    }

    var sortText = catalogCell_(row, headerIndex, "sort_order");
    var sortOrder = parseInt(sortText, 10);
    if (!isFinite(sortOrder)) {
      sortOrder = rowIndex;
    }

    laws.push({
      id: lawId,
      title: title,
      buttonLabel: catalogCell_(row, headerIndex, "button_label") || title,
      emoji: catalogCell_(row, headerIndex, "emoji") || "⚖️",
      directMdFileId: catalogCell_(row, headerIndex, "direct_md_file_id"),
      explainLawName: catalogCell_(row, headerIndex, "explain_law_name"),
      sheetTabName: catalogCell_(row, headerIndex, "sheet_tab_name"),
      active: parseCatalogBoolean_(
        catalogCell_(row, headerIndex, "active")
      ),
      sortOrder: sortOrder
    });
  }

  laws.sort(function(left, right) {
    if (left.sortOrder !== right.sortOrder) {
      return left.sortOrder - right.sortOrder;
    }
    return left.title.localeCompare(right.title);
  });

  return laws;
}

function getPublicLawCatalog_(spreadsheet, config) {
  return getLawCatalog_(spreadsheet, config)
    .filter(function(law) {
      return law.active;
    })
    .map(function(law) {
      return {
        id: law.id,
        title: law.title,
        buttonLabel: law.buttonLabel,
        emoji: law.emoji,
        sortOrder: law.sortOrder
      };
    });
}

function findActiveCatalogLawById_(spreadsheet, config, lawId) {
  lawId = String(lawId || "").trim();
  var laws = getLawCatalog_(spreadsheet, config);

  for (var index = 0; index < laws.length; index++) {
    if (laws[index].id === lawId && laws[index].active) {
      return laws[index];
    }
  }

  return null;
}

function catalogCell_(row, headerIndex, name) {
  var index = headerIndex[name];
  if (index === undefined || !row || row[index] === undefined) {
    return "";
  }
  return String(row[index] || "").trim();
}

function parseCatalogBoolean_(value) {
  var normalized = String(value || "").trim().toLowerCase();
  if (!normalized) {
    return true;
  }
  return ["true", "1", "yes", "y", "active", "on"].indexOf(normalized) >= 0;
}


// ============================================================
// 7. CONFIGURATION AND SECURITY
// ============================================================

function getConfig_() {
  var properties = PropertiesService.getScriptProperties();

  var config = {
    geminiApiKey: String(
      properties.getProperty("GEMINI_API_KEY") || ""
    ).trim(),

    masterIndexId: String(
      properties.getProperty("MASTER_INDEX_ID") || ""
    ).trim(),

    spreadsheetId: String(
      properties.getProperty("SPREADSHEET_ID") || ""
    ).trim(),

    botSharedSecret: String(
      properties.getProperty("BOT_SHARED_SECRET") || ""
    ),

    chatModel: normalizeModelName_(
      properties.getProperty("GEMINI_CHAT_MODEL") ||
      DEFAULT_CONFIG_.chatModel
    ),

    embeddingModel: normalizeModelName_(
      properties.getProperty("GEMINI_EMBEDDING_MODEL") ||
      DEFAULT_CONFIG_.embeddingModel
    ),

    maxSelectedLaws: positiveInteger_(
      properties.getProperty("MAX_SELECTED_LAWS"),
      DEFAULT_CONFIG_.maxSelectedLaws
    ),

    topKPerVectorFile: positiveInteger_(
      properties.getProperty("TOP_K_PER_VECTOR_FILE"),
      DEFAULT_CONFIG_.topKPerVectorFile
    ),

    topArticlesPerLaw: positiveInteger_(
      properties.getProperty("TOP_ARTICLES_PER_LAW"),
      DEFAULT_CONFIG_.topArticlesPerLaw
    ),

    maxContextChars: positiveInteger_(
      properties.getProperty("MAX_CONTEXT_CHARS"),
      DEFAULT_CONFIG_.maxContextChars
    ),

    maxOutputTokens: positiveInteger_(
      properties.getProperty("MAX_OUTPUT_TOKENS"),
      DEFAULT_CONFIG_.maxOutputTokens
    ),

    lawCatalogSheet: String(
      properties.getProperty("LAW_CATALOG_SHEET") ||
      DEFAULT_CONFIG_.lawCatalogSheet
    ).trim()
  };

  var missing = [];

  if (!config.geminiApiKey) {
    missing.push("GEMINI_API_KEY");
  }

  if (!config.masterIndexId) {
    missing.push("MASTER_INDEX_ID");
  }

  if (!config.spreadsheetId) {
    missing.push("SPREADSHEET_ID");
  }

  if (missing.length > 0) {
    throw new Error(
      "Missing Script Properties: " + missing.join(", ")
    );
  }

  return config;
}

function verifySharedSecret_(input, config) {
  if (!config.botSharedSecret) {
    return;
  }

  var providedSecret = String(input.apiKey || "");
  if (!secureEquals_(providedSecret, config.botSharedSecret)) {
    throw new Error("Unauthorized GAS request");
  }
}

function secureEquals_(left, right) {
  left = String(left || "");
  right = String(right || "");

  var mismatch = left.length ^ right.length;
  var maxLength = Math.max(left.length, right.length);

  for (var index = 0; index < maxLength; index++) {
    var leftCode = index < left.length ? left.charCodeAt(index) : 0;
    var rightCode = index < right.length ? right.charCodeAt(index) : 0;
    mismatch |= leftCode ^ rightCode;
  }

  return mismatch === 0;
}


// ============================================================
// 7. DATA VALIDATION AND GENERAL HELPERS
// ============================================================

function validateMasterIndex_(masterIndex) {
  for (var index = 0; index < masterIndex.length; index++) {
    var law = masterIndex[index];

    if (!law || typeof law !== "object") {
      throw new Error("Master Index item " + index + " is not an object");
    }

    if (!String(law.law_name || "").trim()) {
      throw new Error("Master Index item " + index + " has no law_name");
    }

    if (!law.file_id || (Array.isArray(law.file_id) && law.file_id.length === 0)) {
      throw new Error(
        "Master Index item " + law.law_name + " has no file_id"
      );
    }
  }
}

function findLawInfo_(masterIndex, lawId) {
  lawId = String(lawId || "").trim();

  for (var index = 0; index < masterIndex.length; index++) {
    if (String(masterIndex[index].law_name || "").trim() === lawId) {
      return masterIndex[index];
    }
  }

  return null;
}

function parseAndValidateLawIds_(rawAnswer, masterIndex) {
  var text = String(rawAnswer || "")
    .replace(/```(?:json|text)?/gi, "")
    .replace(/```/g, "")
    .trim();

  var candidates = [];

  if (text.charAt(0) === "[") {
    try {
      var parsed = JSON.parse(text);
      if (Array.isArray(parsed)) {
        candidates = parsed;
      }
    } catch (ignored) {
      // Fall through to delimiter parsing.
    }
  }

  if (candidates.length === 0) {
    candidates = text.split(/[,;\n]+/);
  }

  var allowed = {};
  for (var index = 0; index < masterIndex.length; index++) {
    var allowedId = String(masterIndex[index].law_name || "").trim();
    if (allowedId) {
      allowed[allowedId] = true;
    }
  }

  var valid = [];
  var seen = {};

  for (var candidateIndex = 0; candidateIndex < candidates.length; candidateIndex++) {
    var candidate = String(candidates[candidateIndex] || "")
      .replace(/^[-*•\s]+/, "")
      .replace(/^\d+[.)]\s*/, "")
      .replace(/^ID\s*:\s*/i, "")
      .replace(/^["']|["']$/g, "")
      .trim();

    if (allowed[candidate] && !seen[candidate]) {
      seen[candidate] = true;
      valid.push(candidate);
    }
  }

  if (valid.length === 0) {
    throw new Error(
      "Gemini router returned no valid IDs. Raw output: " +
      text.substring(0, 500)
    );
  }

  return valid;
}

function safeJsonParse_(jsonString, label) {
  var text = String(jsonString || "")
    .replace(/^\uFEFF/, "")
    .trim();

  try {
    return JSON.parse(text);
  } catch (firstError) {
    // Compatibility fallback for files containing illegal control characters.
    var sanitized = text.replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F-\u009F]/g, "");

    try {
      return JSON.parse(sanitized);
    } catch (secondError) {
      throw new Error(
        (label || "JSON") + " parse error: " + secondError.message
      );
    }
  }
}

function uniqueStrings_(items) {
  var result = [];
  var seen = {};

  for (var index = 0; index < items.length; index++) {
    var value = String(items[index] || "").trim();
    if (value && !seen[value]) {
      seen[value] = true;
      result.push(value);
    }
  }

  return result;
}

function normalizeModelName_(modelName) {
  return String(modelName || "")
    .trim()
    .replace(/^models\//, "");
}

function positiveInteger_(value, fallback) {
  var parsed = parseInt(value, 10);
  return isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function isRetryableError_(error) {
  var message = getErrorMessage_(error).toLowerCase();
  return (
    message.indexOf("http 429") >= 0 ||
    message.indexOf("http 500") >= 0 ||
    message.indexOf("http 502") >= 0 ||
    message.indexOf("http 503") >= 0 ||
    message.indexOf("temporarily") >= 0 ||
    message.indexOf("timed out") >= 0
  );
}

function getErrorMessage_(error) {
  if (!error) {
    return "Unknown error";
  }

  if (error.message) {
    return String(error.message);
  }

  return String(error);
}

function jsonResponse_(data) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}


// ============================================================
// 8. TEST AND DIAGNOSTIC FUNCTIONS
// ============================================================

/**
 * Step 1: confirms that the Apps Script runtime works.
 */
function testBasic_() {
  console.log("BASIC TEST OK");
  return "OK";
}

/**
 * Step 2: validates required Script Properties without logging secrets.
 */
function testConfiguration_() {
  var config = getConfig_();

  console.log("Configuration OK");
  console.log("Chat model: " + config.chatModel);
  console.log("Embedding model: " + config.embeddingModel);
  console.log("Master Index configured: " + Boolean(config.masterIndexId));
  console.log("Spreadsheet configured: " + Boolean(config.spreadsheetId));
  console.log("Shared secret enabled: " + Boolean(config.botSharedSecret));
}

/**
 * Step 3: tests Drive, Master Index, and Spreadsheet access.
 */
function testDriveAndIndex_() {
  var config = getConfig_();

  console.log("STEP 1: Reading Master Index");
  var masterIndex = readJsonDriveFile_(
    config.masterIndexId,
    "Master Index"
  );

  console.log("STEP 2: Master Index items = " + masterIndex.length);
  validateMasterIndex_(masterIndex);

  console.log("STEP 3: Opening Spreadsheet");
  var spreadsheet = getSpreadsheet_(config);
  console.log("Spreadsheet name: " + spreadsheet.getName());

  console.log("STEP 4: Reading LAW_CATALOG");
  var laws = getLawCatalog_(spreadsheet, config);
  console.log("LAW_CATALOG rows: " + laws.length);
  console.log("Active laws: " + laws.filter(function(law) {
    return law.active;
  }).length);

  console.log("DRIVE, INDEX, SHEET, AND LAW_CATALOG TEST OK");
}

/**
 * Step 4: tests Gemini generateContent and embedding independently.
 */
function testGeminiOnly_() {
  var config = getConfig_();

  console.log("STEP 1: Testing Gemini final answer model");
  var answer = askGemini_(
    "តើកិច្ចសន្យាជាអ្វី?",
    "កិច្ចសន្យាគឺជាកិច្ចព្រមព្រៀងរវាងបុគ្គលពីរនាក់ ឬច្រើននាក់។",
    config
  );

  console.log("Gemini sample: " + answer.substring(0, 300));

  console.log("STEP 2: Testing Gemini embedding model");
  var embedding = getGeminiEmbedding_("សាកល្បង embedding", config);
  console.log("Embedding dimensions: " + embedding.length);

  console.log("GEMINI TEST OK");
}

/**
 * Step 5: runs the complete search without swallowing errors.
 */
function testMySearch() {
  var config = getConfig_();
  var spreadsheet = getSpreadsheet_(config);
  var laws = getLawCatalog_(spreadsheet, config).filter(function(law) {
    return law.active;
  });

  if (laws.length === 0) {
    throw new Error("LAW_CATALOG has no active laws");
  }

  var question = "រៀងរាប់លំហូរនីតិវិធីអនុវត្តដោយបង្ខំ";
  var result = answerFromExistingSystem_(
    question,
    {
      mode: "explain",
      lawId: laws[0].id
    },
    config
  );

  console.log("Test law_id: " + laws[0].id);
  console.log("Selected laws: " + result.selectedLawIds.join(", "));
  console.log("Context characters: " + result.contextCharacters);
  console.log("FINAL ANSWER:\n" + result.answer);
}

/**
 * Step 6: simulates the exact JSON POST sent by the Telegram bot.
 */
function testDoPost_() {
  var config = getConfig_();
  var spreadsheet = getSpreadsheet_(config);
  var laws = getLawCatalog_(spreadsheet, config).filter(function(law) {
    return law.active;
  });

  if (laws.length === 0) {
    throw new Error("LAW_CATALOG has no active laws");
  }

  var fakeEvent = {
    postData: {
      contents: JSON.stringify({
        action: "ask",
        question: "រៀងរាប់លំហូរនីតិវិធីអនុវត្តដោយបង្ខំ",
        mode: "explain",
        model: config.chatModel,
        lawId: laws[0].id,
        lawTitle: laws[0].title,
        apiKey: config.botSharedSecret || ""
      })
    }
  };

  var response = doPost(fakeEvent);
  console.log(response.getContent());
}

/**
 * Tests the exact action=list_laws request used by the Telegram first screen.
 */
function testListLaws_() {
  var config = getConfig_();
  var fakeEvent = {
    postData: {
      contents: JSON.stringify({
        action: "list_laws",
        apiKey: config.botSharedSecret || ""
      })
    }
  };

  var response = doPost(fakeEvent);
  console.log(response.getContent());
}
