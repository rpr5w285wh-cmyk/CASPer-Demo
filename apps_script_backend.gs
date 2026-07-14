/**
 * apps_script_backend.gs — CASPer dry-run response collector
 *
 * Paste this whole file into Extensions → Apps Script in the target
 * Google Sheet's project (or any Apps Script project), replace
 * PLACEHOLDER_SHEET_ID, then deploy as a Web App:
 *   Deploy → New deployment → Web app
 *   Execute as: Me
 *   Who has access: Anyone
 *
 * The frontend POSTs a JSON string with Content-Type text/plain
 * (deliberate — Apps Script does not answer CORS preflight requests,
 * so application/json POSTs fail from browsers). e.postData.contents
 * carries the raw JSON either way.
 */

var SHEET_ID = "PLACEHOLDER_SHEET_ID";   // ← Google Sheet ID from its URL
var FOLDER_ID = "PLACEHOLDER_FOLDER_ID"; // ← Drive folder ID for video files (video sessions only)
var SHEET_NAME = "";                     // optional: a specific tab name; "" = first sheet
var EXPECTED_COLUMNS = ["timestamp", "student_id", "prompt_id", "question_id",
                        "response_type", "response", "video_link", "mock"];

/** Health check: open the Web App URL in a browser to confirm it's live. */
function doGet(e) {
  return jsonResponse({
    status: "ok",
    message: "This endpoint is live — POST responses here.",
    typed_body: '{"student_id":"...","mock":"1","prompt_id":"...","timestamp":"...","answers":[{"question_id":"A","response":"..."}]}',
    video_body: '{"type":"video","student_id":"...","mock":"1","prompt_id":"...","question_id":"A","timestamp":"...","mime_type":"video/webm","video_base64":"..."}'
  });
}

/**
 * Typed submissions: one row per question
 *   [timestamp, student_id, prompt_id, question_id, "typed", response, "", mock]
 * Video submissions (type:"video", one question per POST): file saved to the
 * Drive folder, then
 *   [timestamp, student_id, prompt_id, question_id, "video", "", file URL, mock]
 * The blank response column is filled later by the transcription step.
 * Rows are ONLY ever appended — the same student_id submitting again (a
 * second mock, or a restart) must never be deduped or blocked here.
 */
function doPost(e) {
  var lock = LockService.getScriptLock();
  try {
    // Serialize concurrent submissions so appendRow calls don't race.
    lock.waitLock(15000);

    if (!e || !e.postData || !e.postData.contents) {
      return jsonResponse({ status: "error", message: "Empty request body" });
    }

    var data;
    try {
      data = JSON.parse(e.postData.contents);
    } catch (parseErr) {
      return jsonResponse({ status: "error", message: "Body is not valid JSON" });
    }

    var studentId = String(data.student_id || "").trim();
    var promptId  = String(data.prompt_id  || "").trim();
    var timestamp = String(data.timestamp  || "").trim() || new Date().toISOString();
    // Which sitting this is (?mock= on the student link). Tolerates anything;
    // blank when the link carried no mock parameter.
    var mock      = String(data.mock || "").trim();
    if (!studentId || !promptId) {
      return jsonResponse({ status: "error", message: "Missing student_id or prompt_id" });
    }

    var sheet = openSheet_();
    ensureHeader_(sheet);

    // ---- video branch ----
    if (data.type === "video") {
      var qid = String(data.question_id || "A").trim();
      if (!data.video_base64) {
        // Camera failed client-side: record the fact as a row so the
        // scenario isn't silently missing from the sheet.
        var noteText = String(data.note || "no recording captured");
        sheet.appendRow([timestamp, studentId, promptId, qid, "video",
                         "(recording failed: " + noteText + ")", "", mock]);
        return jsonResponse({ status: "ok", message: "Failure row appended",
                              student_id: studentId, prompt_id: promptId, question_id: qid });
      }
      var mime = String(data.mime_type || "video/webm");
      var ext = mime.indexOf("mp4") >= 0 ? "mp4" : "webm";
      // Filename encodes identity so transcription can run without a join.
      // student_id (an email) is sanitized so an odd character can never break
      // the Drive upload; the mock segment goes AFTER the timestamp because
      // transcribe.py reads parts[0..3] as id/prompt/question/timestamp.
      var safeId = studentId.replace(/[^A-Za-z0-9@._-]/g, "_");
      var safeMock = mock.replace(/[^A-Za-z0-9._-]/g, "_");
      var fname = safeId + "__" + promptId + "__" + qid + "__" +
                  timestamp.replace(/[:.]/g, "-") +
                  (safeMock ? "__mock" + safeMock : "") + "." + ext;
      var bytes = Utilities.base64Decode(data.video_base64);
      var blob = Utilities.newBlob(bytes, mime, fname);
      var file = DriveApp.getFolderById(FOLDER_ID).createFile(blob);
      sheet.appendRow([timestamp, studentId, promptId, qid, "video", "", file.getUrl(), mock]);
      return jsonResponse({ status: "ok", message: "Video saved: " + fname,
                            student_id: studentId, prompt_id: promptId, question_id: qid });
    }

    // ---- typed branch (answers array; legacy single-response supported) ----
    var answers = data.answers;
    if (!answers || !answers.length) {
      answers = [{ question_id: "A", response: String(data.response || "") }];
    }
    var written = 0;
    for (var i = 0; i < answers.length; i++) {
      var q = String(answers[i].question_id || "A").trim();
      var resp = String(answers[i].response || "").trim();
      // Blank answers are recorded too — an empty cell under time pressure
      // is real data for the dry-run, not an error.
      sheet.appendRow([timestamp, studentId, promptId, q, "typed", resp, "", mock]);
      written++;
    }
    return jsonResponse({ status: "ok", message: written + " row(s) appended",
                          student_id: studentId, prompt_id: promptId, timestamp: timestamp });

  } catch (err) {
    return jsonResponse({ status: "error", message: "Server error: " + err });
  } finally {
    try { lock.releaseLock(); } catch (ignore) {}
  }
}

/** Opens the target sheet (specific tab if SHEET_NAME set, else first tab). */
function openSheet_() {
  var ss = SpreadsheetApp.openById(SHEET_ID);
  if (SHEET_NAME) {
    var named = ss.getSheetByName(SHEET_NAME);
    if (named) return named;
  }
  return ss.getSheets()[0];
}

/** Writes the header row once if the sheet is empty. */
function ensureHeader_(sheet) {
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(EXPECTED_COLUMNS);
  }
}

/** JSON output helper. */
function jsonResponse(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
