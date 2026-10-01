/* English / 繁體中文 for the participant page — the same shape as the hub's
   launcher_web/i18n.js and the desktop's core/i18n.py: the English source
   string is the key, only Chinese is stored, and anything untranslated shows
   in English rather than blank.

     t("Hello, {name}", {name})   a string app.js renders
     translate(text)              a string the engine produced (a `reason`, an
                                  edge hint): looked up whole, else matched by
                                  ZH_RULES, since some are formatted with
                                  numbers before they get here
     applyStatic()                every [data-t] element in the page, keyed by
                                  its own English markup

   The engine strings reuse core/i18n_zh.py's wording exactly, so a
   participant and a desktop patient are told the same thing.

   tests/i18n_check.mjs walks app.js and index.html and fails on a string with
   no entry here. Pure apart from applyStatic()/setLang(), which touch the
   document only when there is one. */

export const ZH = {
  // ── fixed page text (index.html, data-t) ──
  "Just a moment.": "請稍候。",
  "Thank you": "謝謝您",
  "Do the check again": "再做一次",
  "It takes about two minutes.": "大約需要兩分鐘。",
  "Your camera picture stays on this phone. It is never sent anywhere.": "鏡頭畫面只留在這支手機上，不會傳送到任何地方。",
  "I'm ready": "我準備好了",
  "This is a wellness check, not a medical test. It cannot diagnose anything.": "這是健康自我檢查，不是醫療檢驗，無法做出任何診斷。",
  "Which hand will you use?": "您要用哪一隻手？",
  "Choose the hand you will tap with.": "請選擇您要用來敲擊的手。",
  "Left hand": "左手",
  "Right hand": "右手",
  "Next, we need the camera": "接下來需要使用鏡頭",
  "Your phone will ask for permission. Please choose <b>Allow</b>.": "手機會詢問是否允許，請選擇<b>允許</b>。",
  "The picture stays on your phone. Nobody sees it, and nothing is recorded.": "畫面只留在您的手機上，沒有人會看到，也不會錄影。",
  "Turn on the camera": "開啟鏡頭",
  "The camera is switched off": "鏡頭目前已關閉",
  "We cannot do the test without it. Here is how to switch it back on.": "沒有鏡頭就無法進行測驗。以下是重新開啟的方法。",
  "I've done that — try again": "我已經設定好了 — 再試一次",
  "Stand your phone up": "把手機立起來",
  "Lean it against something so you don't have to hold it. Sit about an arm's length away.": "把手機靠在東西上，不用拿在手裡。坐在大約一個手臂遠的地方。",
  "Next": "下一步",
  "Open and close your hand": "把手張開再合起來",
  "Touch your thumb and finger together, then open them wide. Do that a few times, slowly.": "讓拇指和食指碰在一起，再盡量張開。慢慢地做幾次。",
  "Let's practise": "先來練習",
  "Tap your thumb and first finger together, as big and as fast as you can.": "用拇指和食指互相敲擊，動作盡量大、盡量快。",
  "I'm ready to start": "我準備好開始了",
  "Let me practise more": "我想再練習一下",
  "Tap as big and as fast as you can until we say stop.": "盡量大、盡量快地敲擊，直到我們說停為止。",
  "Paused — your hand is out of view": "已暫停 — 您的手不在畫面內",
  "All done": "完成了",
  "We could not send the result yet. It is saved on this phone and will be sent when you are back online.": "結果還沒送出。結果已存在這支手機上，恢復連線後會自動送出。",
  "Try sending again": "再試著送出",
  "This is a screening tool, not a medical diagnosis. Please talk to a healthcare professional about anything that concerns you.": "這是篩檢工具，不是醫療診斷。如有任何疑慮，請諮詢醫療專業人員。",
  "Let's try that again": "我們再試一次",
  "Try again": "再試一次",
  "Please turn your phone upright": "請把手機轉成直立",
  "Read aloud": "朗讀",
  "Bigger text": "放大字體",
  "Start over": "重新開始",

  // ── app.js ──
  "the person who invited you": "邀請您的人",
  "The question appears at the <b>top of the screen</b>. Tap <b>Allow</b>.": "詢問會出現在<b>螢幕上方</b>，請點<b>允許</b>。",
  "The question appears near the <b>top of the screen</b>. Tap <b>Allow</b> or <b>While using the app</b>.": "詢問會出現在<b>螢幕上方</b>附近，請點<b>允許</b>或<b>使用應用程式時</b>。",
  "Open the <b>Settings</b> app on your phone.": "打開手機的<b>設定</b>。",
  "Scroll down and tap <b>Safari</b>.": "往下捲動，點<b>Safari</b>。",
  "Tap <b>Camera</b>, then choose <b>Ask</b> or <b>Allow</b>.": "點<b>相機</b>，再選擇<b>詢問</b>或<b>允許</b>。",
  "Come back here and tap the button below.": "回到這裡，點下方的按鈕。",
  "Tap the <b>lock</b> or <b>sliders</b> icon next to the web address at the top.": "點上方網址旁邊的<b>鎖頭</b>或<b>設定</b>圖示。",
  "Tap <b>Permissions</b>, then <b>Camera</b>.": "點<b>權限</b>，再點<b>相機</b>。",
  "Choose <b>Allow</b>.": "選擇<b>允許</b>。",
  "Please open this in your browser": "請用瀏覽器開啟",
  "Camera tests do not work inside {app}.": "在 {app} 裡面無法使用鏡頭測驗。",
  "Camera tests do not work inside this app.": "在這個應用程式裡面無法使用鏡頭測驗。",
  "Tap the <b>&#8943;</b> or <b>&#8942;</b> menu in the corner of this screen, then choose <b>Open in Safari</b>.": "點畫面角落的 <b>&#8943;</b> 或 <b>&#8942;</b> 選單，再選擇<b>用 Safari 開啟</b>。",
  "Tap the <b>&#8943;</b> or <b>&#8942;</b> menu in the corner of this screen, then choose <b>Open in Chrome</b>.": "點畫面角落的 <b>&#8943;</b> 或 <b>&#8942;</b> 選單，再選擇<b>用 Chrome 開啟</b>。",
  "This phone cannot run the test": "這支手機無法進行測驗",
  "The camera is not available in this browser.": "這個瀏覽器無法使用鏡頭。",
  "Please try again in Safari or Chrome.": "請改用 Safari 或 Chrome 再試一次。",
  "This link is incomplete": "這個連結不完整",
  "The web address is missing its last part.": "網址缺少了最後一段。",
  "Please ask for the link again, and open it by tapping it rather than typing it.": "請再要一次連結，並直接點開，不要手動輸入。",
  "Not quite ready yet": "還沒準備好",
  "This link is not switched on at the other end.": "對方還沒有開啟這個連結。",
  "Please let the person who sent it know.": "請告訴傳連結給您的人。",
  "We could not check this link": "無法確認這個連結",
  "Something went wrong reaching the internet.": "連上網路時發生問題。",
  "Check your connection, then try again.": "請檢查網路連線，再試一次。",
  "This link cannot be used": "這個連結無法使用",
  "Ask the person who sent it for a new one.": "請向傳連結給您的人要一個新的。",
  "This test is not ready yet": "這項測驗還沒準備好",
  "This link is for a test that cannot be done on a phone yet.": "這個連結的測驗目前還不能在手機上進行。",
  "You have already done this check. Your result was saved for {name}.": "您已經做過這項檢查了。結果已為 {name} 保存。",
  "Hello, {name}": "{name}，您好",
  "Hello": "您好",
  "{name} has asked you to do a short finger-tapping check.": "{name} 邀請您做一個簡短的手指敲擊檢查。",
  "Only the measurements are sent, and only to <b>{name}</b>.": "只會傳送測量數值，而且只傳給 <b>{name}</b>。",
  "That link is not valid.": "這個連結無效。",
  "That link was cancelled.": "這個連結已被取消。",
  "That link has expired. Ask for a new one.": "這個連結已過期，請要一個新的。",
  "That link has already been used.": "這個連結已經使用過了。",
  "We cannot reach the camera": "無法使用鏡頭",
  "Another app may be using it.": "可能有其他應用程式正在使用鏡頭。",
  "Close your other apps, then try again.": "請關閉其他應用程式，再試一次。",
  "Getting ready…": "準備中…",
  "We could not start the test": "無法開始測驗",
  "The hand-tracking part did not load.": "手部追蹤功能沒有載入成功。",
  "Hold your hand up, so the camera can see it.": "請把手舉起來，讓鏡頭看得到。",
  "Come a little closer.": "請靠近一點。",
  "Move back a little.": "請往後退一點。",
  "Close your other apps. This phone is busy.": "請關閉其他應用程式，這支手機目前太忙了。",
  "That's it. Hold still.": "就是這樣，請保持不動。",
  "Touch them together…": "讓兩指碰在一起…",
  "Good. {n} of {total}": "很好，第 {n} 次，共 {total} 次",
  "We could not see your hand opening and closing clearly. Let's try once more, a little slower.": "我們沒辦法清楚看到您的手張開和合起。請再試一次，動作慢一點。",
  "Tap a few times to try it.": "敲幾下試試看。",
  "Good. You're ready when you are.": "很好，您準備好就可以開始。",
  "That's a tap. Good.": "這算一次敲擊，很好。",
  "Open your fingers wider between taps.": "每次敲擊之間，手指請張得更開。",
  "Get ready": "準備",
  "Go": "開始",
  "Go!": "開始！",
  "Your hand was out of view for too long. Let's try again with the phone a little further away.": "您的手離開畫面太久了。請把手機放遠一點，再試一次。",
  "This phone was working too hard to measure accurately. Close your other apps and try again.": "這支手機負荷太重，無法準確測量。請關閉其他應用程式，再試一次。",
  "Your hand went out of view during the test. Let's try again with the phone a little further away.": "測驗中您的手離開了畫面。請把手機放遠一點，再試一次。",
  "We could not score that attempt.": "這次無法計分。",
  "Thank you. Your result is ready for {name}.": "謝謝您。您的結果已準備好給 {name}。",
  "taps in {secs} seconds": "次敲擊（{secs} 秒內）",
  "Sending your result…": "正在送出結果…",
  "Saved and sent to {name}.": "已保存並送給 {name}。",

  // ── engine strings, as core/i18n_zh.py says them ──
  "Show your hand to the camera": "請將手對準鏡頭",
  "Move your hand toward the middle": "請將手移向畫面中央",
  "Raise your hand a little": "請將手稍微抬高",
  "Lower your hand a little": "請將手稍微放低",
  "Move your hand back from the screen": "請將手往後移，離螢幕遠一點",
  "Your hand was out of view for part of the test - keep it in the frame and try again.":
    "測驗過程中您的手有一段時間不在畫面內，請保持手在畫面中並再試一次。",
  "Tapping was too irregular to score - large pauses interrupted the rhythm. Try to keep a continuous motion.":
    "敲擊過於不規律而無法計分 — 中間出現較長的停頓，打斷了節奏。請盡量保持連續動作。",
};

// Strings the engine formatted before handing them over. `$1` takes group 1.
// Same patterns and wording as core/i18n_zh.py ZH_RULES.
export const ZH_RULES = [
  [/^(\d+) closures were too shallow to count as taps - open the hand fully between taps\.$/,
   "有 $1 次合攏幅度太小，未被計為敲擊 — 每次敲擊之間請將手完全張開。"],
  [/^Only (\d+) taps detected - at least (\d+) are needed for a reliable score\.$/,
   "只偵測到 $1 次敲擊 — 可靠的評分至少需要 $2 次。"],
  [/^Tapping was too slow to score a rhythm \((\d+(?:\.\d+)?) taps\/s - long pauses between taps leave no steady rhythm to measure\)\. Try to keep a continuous tapping motion\.$/,
   "敲擊速度太慢，無法評估節奏（每秒 $1 次 — 敲擊之間停頓太久，沒有穩定的節奏可供測量）。請保持連續的敲擊動作。"],
];

let lang = "en";

export function getLang() { return lang; }

/** Substitute {name} params by regex, not a template engine, so a stray
 *  brace in a helper's name can never throw mid-test. */
function fill(text, params) {
  if (!params) return text;
  return text.replace(/\{(\w+)\}/g, (whole, key) =>
    Object.prototype.hasOwnProperty.call(params, key) ? String(params[key]) : whole);
}

/** Chinese for an English string, or null when there is none. */
export function lookup(en) {
  if (Object.prototype.hasOwnProperty.call(ZH, en)) return ZH[en];
  for (const [re, zh] of ZH_RULES) {
    const m = en.match(re);
    if (m) return zh.replace(/\$(\d)/g, (_, i) => m[Number(i)] ?? "");
  }
  return null;
}

export function t(en, params) {
  const out = lang === "zh" ? (lookup(en) ?? en) : en;
  return fill(out, params);
}

/** For text the engine produced, which may carry numbers already. */
export function translate(en) {
  if (lang !== "zh" || !en) return en;
  return lookup(en) ?? en;
}

/** The English key a [data-t] element is looked up by: its own markup, with
 *  whitespace collapsed. Kept on the element so switching back restores it. */
export function keyOf(html) {
  return String(html).replace(/\s+/g, " ").trim();
}

export function applyStatic(root) {
  if (typeof document === "undefined") return;
  for (const el of (root || document).querySelectorAll("[data-t]")) {
    if (el.dataset.en === undefined) el.dataset.en = keyOf(el.innerHTML);
    const en = el.dataset.en;
    el.innerHTML = lang === "zh" ? (lookup(en) ?? en) : en;
  }
}

export function setLang(next) {
  lang = next === "zh" ? "zh" : "en";
  if (typeof document !== "undefined") {
    document.documentElement.lang = lang === "zh" ? "zh-Hant" : "en";
    applyStatic();
  }
}
