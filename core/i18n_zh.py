"""
繁體中文 overlay strings. Chinese only — see core/i18n.py for why.

House style, carried over from launcher_web/i18n.zh.js: **translate the prose,
keep the term.** Metric acronyms (CV, IIV, SD, SPARC), units (Hz, ms, %, s),
identifiers, file paths and citations stay Latin.

Three kinds of entry:

  "English source string": "中文"        looked up by t()
  "dotted.key": ["第一行", "第二行"]      looked up by tk(), for the pre-split
                                         instruction blocks; the line count
                                         need not match the English
  ZH_RULES                               regex table for strings the engine has
                                         already formatted (metrics.py reasons,
                                         which are also saved to results/*.json
                                         and so cannot become templates)

Covers the shared UI toolkit and all four tools — finger tapping, spiral
tracing, the oculomotor test and the hand-tracking inspector (phases 1-2 of
docs/OVERLAY_I18N_PLAN.md). The console splash and the camera prompt are
phase 3 and are not here yet.
"""

import re

ZH: dict[str, object] = {

    # ── Shared UI toolkit (core/ui) ────────────────────────────────────────
    "Motor Screening": "動作篩檢",
    "Screening tool, not a diagnosis - consult a healthcare professional.":
        "此為篩檢工具，並非診斷結果",

    # ── Buttons ────────────────────────────────────────────────────────────
    "Start Test": "開始測驗",
    "I'm Ready": "我準備好了",
    "Try Again": "再試一次",
    "Start {mode} ({secs} s)": "開始{mode}（{secs} 秒）",
    "{mode} ({secs} s, with metronome)": "{mode}（{secs} 秒，含節拍器）",

    # ── Countdown / phase banners ──────────────────────────────────────────
    "Get ready...": "準備開始…",
    "Get ready to start": "準備開始",
    "Your Task": "測驗說明",
    "{mode} - Your Task": "{mode} — 測驗說明",
    "{mode} - Results": "{mode} — 測驗結果",
    "Practice - not scored yet": "練習中 — 尚未計分",
    "Scored test begins in {secs} s": "正式測驗將於 {secs} 秒後開始",
    "warm-up": "暖身",
    "{secs} s left": "剩餘 {secs} 秒",

    # ── Hand-presence chips and coach messages ─────────────────────────────
    "Hand detected": "已偵測到手部",
    "Show your hand": "請將手放入畫面",
    "Show your hand to the camera": "請將手對準鏡頭",
    "Keep your hand in the frame": "請讓手保持在畫面內",
    "Having trouble? Move a little closer to the camera":
        "有困難嗎？請將手稍微靠近鏡頭",

    # ── Finger tapping: title screen ───────────────────────────────────────
    "Finger Tapping Test": "手指敲擊測驗",
    "Measures motor rhythm and speed -": "測量動作節奏與速度 —",
    "markers studied in early cognitive decline.":
        "這是早期認知衰退研究中的指標。",

    # ── Finger tapping: mode names (drawn only; the data keeps English) ────
    "Big & Fast": "大動作快速敲擊",
    "Paced Rhythm": "節拍同步敲擊",

    # ── Finger tapping: instructions, wrapped for Chinese line lengths ─────
    "tap.big_and_fast.instructions": [
        "請使用您慣用的那隻手：",
        "將食指與拇指互相敲擊，",
        "動作盡量大、速度盡量快。",
        "完全張開、完全合攏 — 持續 20 秒。",
    ],
    "tap.paced.instructions": [
        "請使用您慣用的那隻手：",
        "每聽到一次嗶聲，就用食指",
        "敲擊拇指一次 — 一聲一下。",
        "測量的是您節奏的穩定度，",
        "而不是與節拍完全對齊的準確度。",
    ],
    "Next: a quick warm-up so we can calibrate to your hand.":
        "接下來是簡短暖身，讓系統校正您的手部動作。",

    # ── Finger tapping: calibration ────────────────────────────────────────
    "Warm-up: open and close your hand": "暖身：請反覆張開與合攏手掌",
    "Touch index finger to thumb, then open wide - a few times.":
        "食指碰拇指，再完全張開 — 重複幾次。",

    # ── Finger tapping: live readout ───────────────────────────────────────
    "Taps": "次數",
    "Rate": "頻率",

    # ── Finger tapping: results ────────────────────────────────────────────
    "Rhythm variability (CV of tap intervals)": "節奏變異度（敲擊間隔的 CV）",
    "Tap rate": "敲擊頻率",
    "Mean interval": "平均間隔",
    "IIV (SD)": "IIV（標準差）",
    "Amplitude CV": "振幅 CV",
    "Speed change": "速度變化",
    "Beat sync SD": "節拍同步 SD",
    "Beats hit": "命中節拍",
    "Intervals": "有效間隔",
    "95% CI {low}-{high}%": "95% 信賴區間 {low}-{high}%",
    "High": "高",
    "Moderate": "中等",
    "Low": "低",
    "Measurement confidence": "測量信賴度",
    "{level} - {pct}%": "{level}信賴度 — {pct}%",
    "Result saved": "結果已儲存",
    "Close to a band edge - repeat for a firmer reading.":
        "接近分級邊界 — 建議重測以取得更穩定的結果。",
    "Typical < {typical}% | monitor {typical}-{monitor}% | elevated > {monitor}%":
        "典型 < {typical}% ｜ 追蹤 {typical}-{monitor}% ｜ 偏高 > {monitor}%",
    "Saved: results/{name}": "已儲存：results/{name}",

    # ── Finger tapping: bands (core/tapping/metrics.py, drawn only) ────────
    "Within typical range": "在典型範圍內",
    "Mild variability - consider monitoring": "輕微變異 — 建議持續追蹤",
    "Elevated variability - recommend follow-up": "變異偏高 — 建議進一步追蹤檢查",

    # ── Failure states ─────────────────────────────────────────────────────
    "Couldn't score this run": "這次無法計分",
    "Something went wrong - please try again.": "發生問題 — 請再試一次。",
    "Your hand was out of view for part of the test - keep it in the frame and try again.":
        "測驗過程中您的手有一段時間不在畫面內，請保持手在畫面中並再試一次。",
    "Tapping was too irregular to score - large pauses interrupted the rhythm. Try to keep a continuous motion.":
        "敲擊過於不規律而無法計分 — 中間出現較長的停頓，打斷了節奏。請盡量保持連續動作。",

    # ══ Spiral tracing ═════════════════════════════════════════════════════

    # ── Title screen ───────────────────────────────────────────────────────
    "Spiral Tracing Test": "螺旋描繪測驗",
    "Measures movement smoothness and jitter -": "測量動作流暢度與抖動 —",
    "markers studied in cognitive decline.": "這是認知衰退研究中的指標。",
    "Spiral Tracing": "螺旋描繪",

    # ── Instructions ───────────────────────────────────────────────────────
    "spiral.instructions": [
        "請使用您慣用的那隻手，沿著螺旋線",
        "由中心向外描繪至邊緣 — 以您自己",
        "舒適的速度進行，沒有光點需要追。",
        "請盡量保持動作流暢而穩定。",
    ],
    "{secs}s practice, then trace the spiral once at your pace.":
        "{secs} 秒練習，接著以自己的速度描繪螺旋一次。",

    # ── Warm-up and the centre-hold gate ───────────────────────────────────
    "Follow the dot around the circle": "請跟著光點繞圈",
    "Hold steady...": "請保持穩定…",
    "Move your fingertip onto the center dot to begin.":
        "請將指尖移到中心的圓點上開始。",
    "Show your hand, then touch the center dot":
        "請將手放入畫面，再碰觸中心圓點",

    # ── Live readout ───────────────────────────────────────────────────────
    "Time": "時間",
    "Trace": "進度",
    "trace out to the edge": "描繪至邊緣",

    # ── Results ────────────────────────────────────────────────────────────
    "Spiral Tracing - Results": "螺旋描繪 — 測驗結果",
    "Smoothness index (0-100, higher = smoother)":
        "流暢度指數（0-100，越高越流暢）",
    "Velocity CV": "速度 CV",
    "Norm. jerk": "正規化急動度",
    "Tremor power*": "震顫功率＊",
    "Tremor freq*": "震顫頻率＊",
    "Completion": "完成度",
    "Mean speed": "平均速度",
    "Data frames": "資料影格",
    "Smoothness via SPARC. Provisional bands - screening, not diagnosis.":
        "流暢度以 SPARC 計算。分級為暫定值 — 僅供篩檢，並非診斷。",
    "* tremor metrics are coarse at this frame rate.":
        "＊在此影格率下，震顫指標較為粗略。",

    # ── Bands (core/spiral/metrics.py, drawn only) ─────────────────────────
    "Smoothness unavailable": "無法取得流暢度",
    "Smooth, well-controlled tracing": "描繪流暢且控制良好",
    "Mild jitter - consider monitoring": "輕微抖動 — 建議持續追蹤",
    "Marked jitter - recommend follow-up": "明顯抖動 — 建議進一步追蹤檢查",

    # ── Failure states ─────────────────────────────────────────────────────
    "Could not compute a motion profile from this trace.":
        "無法從這次描繪計算出動作曲線。",
    "Could not compute smoothness from this trace.":
        "無法從這次描繪計算出流暢度。",

    # ══ Oculomotor (eye movement) ══════════════════════════════════════════

    # ── Title screen ───────────────────────────────────────────────────────
    "Eye Movement Test": "眼球運動測驗",
    "Measures how quickly and accurately your eyes": "測量您的眼睛反應的速度與",
    "respond - a marker studied in early cognitive decline.":
        "準確度 — 這是早期認知衰退研究中的指標。",
    "Three short parts, about 3 minutes total.":
        "共三個部分，約 3 分鐘。",
    "Start Eye Movement Test": "開始眼球運動測驗",
    "Sit about arm's length from the screen, face the camera.":
        "請坐在離螢幕約一臂長的位置，並面向鏡頭。",

    # ── Block titles (core/gaze/tasks.py, drawn only) ──────────────────────
    "Part 1 - Look Toward": "第一部分 — 看向光點",
    "Part 2 - Look Away": "第二部分 — 看向反方向",
    "Part 3 - Hold Still": "第三部分 — 保持不動",

    # ── Instructions ───────────────────────────────────────────────────────
    "gaze.pro.instructions": [
        "請將視線保持在中間的 + 上。",
        "當左邊或右邊出現光點時，",
        "請盡快「看向」那個光點，",
        "然後再看回中間。",
    ],
    "gaze.anti.instructions": [
        "請將視線保持在中間的 + 上。",
        "當光點出現時，請看向",
        "「相反」的那一側 — 遠離光點。",
        "這會感覺不自然 — 而這正是測驗重點。",
    ],
    "gaze.fix.instructions": [
        "請將視線保持在中間的 + 上。",
        "不要追視任何東西 — 只要保持不動，",
        "注視中心，直到圓環填滿為止。",
    ],
    "Next: a quick calibration - just look at three dots.":
        "接下來是簡短校正 — 只要看三個圓點。",
    "First a few practice tries, then the scored part.":
        "先做幾次練習，接著進入計分部分。",
    "Last part - about 12 seconds, then you're done.":
        "最後一部分 — 約 12 秒就完成了。",

    # ── Calibration ────────────────────────────────────────────────────────
    "Calibration: look at the glowing dot": "校正中：請注視發光的圓點",
    "Keep your head still - move only your eyes.":
        "請保持頭部不動 — 只移動眼睛。",
    "Show your face to the camera": "請將臉部對準鏡頭",
    "Having trouble? Sit closer and add a little light":
        "有困難嗎？請坐近一點，並增加一些光線",
    "Having trouble? Add light, and raise the camera to eye level so your "
    "lids don't cover the iris":
        "有困難嗎？請增加光線，並將鏡頭調到與視線同高，避免眼皮遮住虹膜",
    "Your eyes are reading as closed - open them wide and hold":
        "您的眼睛被判讀為閉上 — 請將眼睛張大並保持",
    "Eye movement between the dots was too small to measure - move a little closer and retry.":
        "圓點之間的眼球移動太小，無法測量 — 請靠近一點再試一次。",
    "The left and right readings overlapped - keep your head still and retry.":
        "左右兩側的讀值重疊了 — 請保持頭部不動再試一次。",

    # ── Trials ─────────────────────────────────────────────────────────────
    "replacing skipped trials": "補做略過的試驗",
    "Scored part - keep going": "計分部分 — 請繼續",
    "Practice": "練習",
    "practice": "練習",
    "scored": "計分",
    "{label}  -  trial {n} of {total}": "{label} — 第 {n} 次，共 {total} 次",
    "Face the camera": "請面向鏡頭",
    "Open your eyes wide - keep watching the dot":
        "請將眼睛張大 — 並持續注視圓點",
    "Open your eyes wide - keep looking at the +":
        "請將眼睛張大 — 並持續注視 +",

    # ── Eye-opening meter + status chip ────────────────────────────────────
    "Eyes tracked": "已追蹤到眼睛",
    "Eyes not readable": "無法辨識眼睛",
    "Eye opening": "眼睛張開程度",
    "Looking for your eyes...": "正在尋找您的眼睛…",
    "Narrowing - open wider": "眼睛瞇起 — 請張大一些",
    "Eyes read as closed": "眼睛被判讀為閉上",
    "Eyes readable": "眼睛可辨識比例",

    # ── Between-parts summary + redo ───────────────────────────────────────
    "{part} recorded": "{part} 已完成",
    "How this part was recorded - your result comes at the end.":
        "這是本部分的錄製狀況 — 結果會在最後呈現。",
    "Recording quality": "錄製品質",
    "Redo this part": "重做這部分",
    "Redo used": "已重做過",
    "Next part": "下一部分",
    "Finish": "完成",
    "Good": "良好",
    "Fair": "普通",
    "Poor": "不佳",
    "Mean latency": "平均反應時間",
    "Looked toward the dot": "看向圓點次數",
    "Valid trials": "有效試驗",
    "Tracked": "追蹤成功",
    "Hold recorded": "凝視已錄製",
    "not enough data": "資料不足",
    "Fewer usable trials than planned.": "可用試驗少於預期。",
    "Your eyes could not be read for part of this section.":
        "本部分有一段時間無法辨識您的眼睛。",
    "Several trials could not be scored.": "有數次試驗無法計分。",
    "Parts re-recorded": "重做的部分",

    # ── Practice feedback badges ───────────────────────────────────────────
    "Correct": "正確",
    "Look AWAY from the dot": "請看向遠離光點的方向",
    "Look AT the dot": "請看向光點",
    "A little early - wait for the dot": "有點太早 — 請等光點出現",
    "Look back at the +": "請看回中間的 +",
    "Eyes not detected - face the camera": "偵測不到眼睛 — 請面向鏡頭",

    # ── Fixation hold ──────────────────────────────────────────────────────
    "Hold still - keep looking at the +": "保持不動 — 請持續注視 +",
    "hold steady": "保持穩定",

    # ── Results ────────────────────────────────────────────────────────────
    "Eye Movement Test - Results": "眼球運動測驗 — 測驗結果",
    "Anti-saccade errors (looked toward the dot)": "反向掃視錯誤率（看向了光點）",
    "Anti - Pro latency": "反向 − 順向 延遲",
    "Corrected errors": "已修正錯誤",
    "Anti latency": "反向延遲",
    "Pro latency": "順向延遲",
    "Latency CV": "延遲 CV",
    "Valid anti trials": "有效反向試次",
    "Valid pro trials": "有效順向試次",
    "Started too early": "太早開始",
    "Fixation jitter": "注視抖動",
    "Gaze intrusions": "視線闖入",

    # ── Bands (core/gaze/metrics.py + fixation.py, drawn only) ─────────────
    "Mildly elevated - consider monitoring": "輕微偏高 — 建議持續追蹤",
    "Elevated - recommend follow-up": "偏高 — 建議進一步追蹤檢查",
    "Steady fixation": "注視穩定",
    "Mildly unsteady - consider monitoring": "略為不穩 — 建議持續追蹤",
    "Unsteady - recommend follow-up": "不穩定 — 建議進一步追蹤檢查",

    # ── Failure states ─────────────────────────────────────────────────────
    "Your face was out of view for part of the test - sit facing the camera and try again.":
        "測驗過程中您的臉有一段時間不在畫面內 — 請坐正面向鏡頭並再試一次。",
    "Too few eye movements were detected - the dot may be hard to see, or the room too dark.":
        "偵測到的眼球移動太少 — 可能是光點不易看見，或房間光線太暗。",

    # ══ Hand-tracking inspector ════════════════════════════════════════════
    "{name} hand": "{name}手",
    "Left": "左",
    "Right": "右",
    "Closed": "合攏",
    "Open": "張開",
    "Dist": "距離",
    "Landmarks Coordination": "特徵點座標",
    "Wrist": "手腕",
    "Thumb": "拇指",
    "Index": "食指",
    "Middle": "中指",
    "Ring": "無名指",
    "Pinky": "小指",
}


# Strings the engine formatted before storing them. `$1` takes group 1.
ZH_RULES = (
    (re.compile(r"^(\d+) closures were too shallow to count as taps - "
                r"open the hand fully between taps\.$"),
     "$1 次合攏幅度太小，未計為敲擊 — 每次敲擊之間請將手完全張開。"),
    # finger tapping
    (re.compile(r"^Only (\d+) taps detected - at least (\d+) are needed "
                r"for a reliable score\.$"),
     "只偵測到 $1 次敲擊 — 可靠的評分至少需要 $2 次。"),
    (re.compile(r"^(\d+) closures were too shallow to count as taps - "
                r"open the hand fully between taps\.$"),
     "有 $1 次合攏幅度太小，未被計為敲擊 — 每次敲擊之間請將手完全張開。"),
    (re.compile(r"^Tapping was too slow to score a rhythm "
                r"\((\d+(?:\.\d+)?) taps/s - long pauses between taps leave no "
                r"steady rhythm to measure\)\. Try to keep a continuous tapping "
                r"motion\.$"),
     "敲擊速度太慢，無法評估節奏（每秒 $1 次 — 敲擊之間停頓太久，沒有穩定的節奏"
     "可供測量）。請保持連續的敲擊動作。"),
    # oculomotor
    (re.compile(r"^Most trials started before the dot appeared - wait for "
                r"the dot to appear before moving your eyes, then try "
                r"again\.$"),
     "多數試驗在圓點出現前就開始移動 — 請等圓點出現後再移動眼睛，然後再試一次。"),
    (re.compile(r"^Your eyes could only be read on (\d+)% of frames - add "
                r"light, and raise the camera to eye level so your eyelids "
                r"don't cover the iris\.$"),
     "只有 $1% 的影格能辨識到您的眼睛 — 請增加光線，並將鏡頭調到與視線同高，"
     "避免眼皮遮住虹膜。"),
    # spiral tracing
    (re.compile(r"^Not enough data frames \((\d+) < (\d+)\)\. "
                r"Keep your hand visible and try again\.$"),
     "資料影格不足（$1 < $2）。請保持手在畫面內並再試一次。"),
    (re.compile(r"^Trace was too short \(([\d.]+)s\)\. "
                r"Trace the whole spiral outward and try again\.$"),
     "描繪時間過短（$1 秒）。請完整由中心向外描繪並再試一次。"),
    (re.compile(r"^Only (\d+)% of the spiral was traced\. "
                r"Follow the whole line from center to edge\.$"),
     "只描繪了螺旋的 $1%。請沿著整條線由中心描繪到邊緣。"),
    # oculomotor
    (re.compile(r"^Only (\d+) valid anti-saccade trials - at least (\d+) "
                r"are needed for a reliable score\.$"),
     "只有 $1 次有效的反向掃視試次 — 可靠的評分至少需要 $2 次。"),
)
