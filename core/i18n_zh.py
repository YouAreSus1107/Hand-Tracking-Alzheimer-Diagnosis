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
docs/platform/OVERLAY_I18N_PLAN.md), plus the console splash, camera prompt and
start/close lines (phase 3), which are printed through i18n.ct().
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

    # ── Framing: hand partly out of the picture (core/framing.py) ─────────
    "Hand at the edge": "手已到畫面邊緣",
    "Near the edge": "接近畫面邊緣",
    "Move your hand toward the middle": "請將手移向畫面中央",
    "Raise your hand a little": "請將手稍微抬高",
    "Lower your hand a little": "請將手稍微放低",
    "Move your hand back from the screen": "請將手往後移，離螢幕遠一點",
    "Paused - your hand is out of view": "已暫停 — 您的手不在畫面內",
    "The test continues when your whole hand is back.":
        "整隻手回到畫面後，測驗會自動繼續。",
    "Move your hand a little closer to the camera": "請將手稍微靠近鏡頭",

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
    "1 missed tap forgiven": "已略過 1 次漏判的敲擊",
    "1 interruption": "1 次中斷",
    "{n} interruptions": "{n} 次中斷",
    "Speed {pct}% of your usual": "速度為平常的 {pct}%",
    "Slower than your usual - consider monitoring": "比平常慢 — 建議持續觀察",
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
    "First a short practice spiral with pace tips, then the scored spiral.":
        "先描繪一個附有速度提示的小螺旋練習，再進行正式計分的螺旋。",

    # ── Practice spiral: pace gauge, live coaching, done card ──────────────
    "Pace": "速度",
    "Too slow": "太慢",
    "Too fast": "太快",
    "Trace outward along the line": "請沿著線條向外描繪",
    "Go back to the line you were tracing": "請回到您剛才描繪的那一圈線條",
    "Slow down a little": "請稍微放慢",
    "Speed up a little": "請稍微加快",
    "Move more smoothly": "請讓動作更流暢",
    "Good - keep this pace": "很好 — 請保持這個速度",
    "Practice complete": "練習完成",
    "Your time": "您的時間",
    "Recommended time": "建議時間",
    "Time at a good pace": "速度適中的時間",
    "Time near the line": "貼近線條的時間",
    "For the test, move a little faster.": "正式測驗時，請稍微加快速度。",
    "For the test, move a little slower.": "正式測驗時，請稍微放慢速度。",
    "For the test, try to stay closer to the line.":
        "正式測驗時，請盡量貼近線條。",
    "Good pace - keep it for the test.": "速度很好 — 正式測驗時請保持。",
    "Practice Again": "再練習一次",

    # ── The centre-hold gate ───────────────────────────────────────────────
    "Hold steady": "請保持穩定",
    "Put your fingertip on the center dot": "請將指尖移到中心的圓點上",

    # ── Live readout ───────────────────────────────────────────────────────
    "Practice - not scored": "練習 — 不計分",
    "Scored test": "正式測驗",
    "S  skip practice": "S  略過練習",
    "S  skip this part": "S  略過這一部分",
    "V  show instructions": "V  顯示說明",
    "trace out to the edge": "描繪至邊緣",

    # ── Results ────────────────────────────────────────────────────────────
    "Spiral Tracing - Results": "螺旋描繪 — 測驗結果",
    "Norm. jerk": "正規化急動度",
    "Mean deviation": "平均偏離",
    "Line accuracy": "線條準確度",
    "Tremor": "震顫",
    "higher = closer to the line": "越高 = 越貼近線條",
    "higher = more tremor": "越高 = 震顫越明顯",
    "Tremor amplitude": "震顫幅度",
    "Smoothness index": "流暢度指數",
    "Two provisional scores - screening, not diagnosis.":
        "兩個暫定分數 — 僅供篩檢，並非診斷。",
    "No tremor detected": "未偵測到震顫",
    "Mild tremor - consider monitoring": "輕微震顫 — 建議持續追蹤",
    "Marked tremor - recommend follow-up": "明顯震顫 — 建議進一步追蹤檢查",
    "Traced close to the line": "描繪貼近線條",
    "Drifted from the line - consider monitoring": "偏離線條 — 建議持續追蹤",
    "Far from the line - recommend follow-up": "明顯偏離線條 — 建議進一步追蹤檢查",
    "Accurate tracing, no tremor": "描繪準確，未見震顫",
    "Tremor unavailable": "無法計算震顫",
    "Accuracy unavailable": "無法計算準確度",
    "Could not measure this trace.": "無法測量這次描繪。",
    "Tremor freq*": "震顫頻率＊",
    "Completion": "完成度",
    "Mean speed": "平均速度",
    "Data frames": "資料影格",
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
    "Parts skipped": "略過的部分",
    "{part} skipped": "已略過{part}",
    "No error rate - Part 2 skipped": "沒有錯誤率 — 已略過第二部分",
    "All three parts skipped": "三個部分都已略過",
    "Nothing was recorded, so nothing was saved.": "沒有錄到任何資料，因此沒有儲存。",
    "The look-away part was skipped, so there is no error rate to score.":
        "看向反方向的部分已略過，因此沒有錯誤率可評分。",

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
    "Head turned": "頭部移動",
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

    # ══ Speech test (DDK + sustained phonation) ════════════════════════════
    # ── Title screen ───────────────────────────────────────────────────────
    "Speech Test": "說話測驗",
    "Two short parts: speech rhythm and": "兩個簡短部分：說話節奏與",
    "voice steadiness - microphone only.": "聲音穩定度 — 只需要麥克風。",

    # ── Task names (core/speech/tasks.py, drawn only) ──────────────────────
    "Pa-Ta-Ka": "Pa-Ta-Ka 交替音節",
    "Sustained Ahh": "持續發「啊」",

    # ── Instructions, wrapped for Chinese line lengths ─────────────────────
    "ddk.ptk.instructions": [
        "先吸一口氣，然後連續說",
        "PA-TA-KA（ㄆㄚ ㄊㄚ ㄎㄚ）",
        "速度盡量快、節奏盡量平均，",
        "中間不要停，持續 8 秒。",
    ],
    "phon.ahh.instructions": [
        "先吸一口氣，然後發出",
        "「啊————」（AHHH）",
        "用舒服的音高，盡量保持平穩，",
        "持續 6 秒。",
    ],

    # ── Sustained phonation ────────────────────────────────────────────────
    "Hold it steady...": "保持平穩…",
    "Keep the sound going until the bar fills": "請持續發聲，直到進度條填滿",
    "Jitter (cycle-to-cycle pitch variation)": "Jitter（逐週期的音高變化）",
    "Mean pitch": "平均音高",
    "Pitch SD": "音高標準差",
    "Vocal tremor": "聲音顫抖",
    "Voiced": "有聲比例",
    "No steady voice was detected - check that the right microphone is selected and hold the sound a little louder.":
        "沒有偵測到穩定的聲音 — 請確認選擇了正確的麥克風，並把聲音發大聲一點。",
    "The recording was too noisy to measure the voice reliably - move somewhere quieter and try again.":
        "錄音噪音太大，無法可靠地量測聲音 — 請換到安靜一點的地方再試一次。",
    "The voice was too irregular to measure - hold one steady, comfortable pitch and try again.":
        "聲音太不規律，無法量測 — 請保持一個平穩、舒服的音高再試一次。",
    "The voice analysis package (praat-parselmouth) is not installed - run python install.py.":
        "尚未安裝聲音分析套件（praat-parselmouth）— 請執行 python install.py。",
    "Next: a quick microphone check.": "下一步：快速檢查麥克風。",

    # ── Microphone check ───────────────────────────────────────────────────
    "Microphone check": "麥克風檢查",
    "Microphone level": "麥克風音量",
    "Stay quiet for a moment": "請先安靜片刻",
    "Measuring the background noise in the room...": "正在測量房間的背景噪音…",
    "Now say \"{word}\" once, at your normal loudness":
        "現在用平常的音量說一次「{word}」",
    "This sets the level - it is not scored.": "這是用來調整音量，不列入計分。",
    "Continue anyway": "仍要繼續",
    "Sounds good": "聲音清楚",
    "Too loud - move back from the microphone a little":
        "太大聲 — 請離麥克風稍遠一點",
    "Too quiet for this room - speak up or move closer to the microphone":
        "以這個房間來說太小聲 — 請說大聲一點或靠近麥克風",
    "We couldn't hear you - check that the right microphone is selected":
        "聽不到您的聲音 — 請確認選擇了正確的麥克風",

    # ── Status chips ───────────────────────────────────────────────────────
    "Microphone ready": "麥克風就緒",
    "No microphone": "沒有麥克風",
    "Phoneme model on": "音素模型已啟用",
    "Loading phoneme model": "正在載入音素模型",

    # ── Recording + analysis ───────────────────────────────────────────────
    "Go!": "開始！",
    "Go! Keep going...": "開始！繼續說…",
    "Syllables": "音節數",
    "Analysing your recording...": "正在分析您的錄音…",
    "Checking the syllable order with the phoneme model":
        "正在用音素模型檢查音節順序",

    # ── Results ────────────────────────────────────────────────────────────
    "Rhythm variability (CV of syllable intervals)": "節奏變異度（音節間隔的 CV）",
    "Syllable rate": "音節速率",
    "Signal / noise": "訊噪比",

    # ── Microphone errors (core/speech/recorder.py) ────────────────────────
    "The sounddevice package is not installed - run python install.py.":
        "尚未安裝 sounddevice 套件 — 請執行 python install.py。",
    "No microphone was found - plug one in or enable it in the system sound settings.":
        "找不到麥克風 — 請接上麥克風，或在系統音效設定中啟用。",
    "The microphone could not be opened - another app may be using it.":
        "無法開啟麥克風 — 可能有其他應用程式正在使用。",

    # ── Failure states (core/speech/metrics.py) ────────────────────────────
    "The microphone was overloaded (clipping) - move back from it a little and try again.":
        "麥克風音量過載（削波）— 請離麥克風稍遠一點再試一次。",
    "No speech was detected - check that the right microphone is selected and speak a little louder.":
        "沒有偵測到說話聲 — 請確認選擇了正確的麥克風，並說大聲一點。",
    "The recording was too noisy to find syllables reliably - move somewhere quieter and try again.":
        "錄音噪音太大，無法可靠地辨識音節 — 請換到安靜一點的地方再試一次。",
    "Speech was too irregular to score - long pauses interrupted the repetition. Try to keep going without stopping.":
        "說話太不規律，無法計分 — 長時間停頓打斷了重複。請盡量連續說不要停。",

    # ══ Hand tremor ════════════════════════════════════════════════════════
    # ── Title screen ───────────────────────────────────────────────────────
    "Hand Tremor Test": "手部顫抖測驗",
    "Hand Tremor": "手部顫抖",
    "Three 20-second holds with both hands in view.":
        "三段各 20 秒的姿勢，雙手都要在畫面中。",
    "Measures shaking at rest and with arms held out.":
        "測量靜止時與雙臂平舉時的抖動。",

    # ── Phases (core/tremor/phases.py, drawn only) ─────────────────────────
    "Palms Up in Your Lap": "掌心朝上放在腿上",
    "Palms Down in Your Lap": "掌心朝下放在腿上",
    "Arms Held Out": "雙臂平舉",
    "tremor.rest_palm_up.instructions": [
        "往後坐好，雙手放在腿上，",
        "掌心朝上，手指放鬆。",
        "讓手完全放鬆 — 不要刻意保持不動。",
        "雙手都要留在畫面中。",
    ],
    "tremor.rest_palm_down.instructions": [
        "現在把雙手翻過來，",
        "掌心朝下，放在腿上。",
        "讓手完全放鬆 — 不要刻意保持不動。",
        "雙手都要留在畫面中。",
    ],
    "tremor.postural.instructions": [
        "雙臂向前伸直，",
        "掌心朝下，手指輕輕張開。",
        "保持在那個位置，平穩不動，",
        "雙手都要留在畫面中。",
    ],
    "Palms up, hands fully relaxed": "掌心朝上，雙手完全放鬆",
    "Palms down, hands fully relaxed": "掌心朝下，雙手完全放鬆",
    "Aim the camera at your lap before you start.": "開始前，請先把鏡頭對準您的腿上。",
    "Hold both arms out, palms down": "雙臂向前平舉，掌心朝下",
    "Part {n} of {total}": "第 {n} 部分，共 {total} 部分",
    "Hold for {s} seconds. Press Space when ready.":
        "維持 {s} 秒。準備好後按空白鍵。",

    # ── Positioning + recording ────────────────────────────────────────────
    "Place both hands in view": "請讓雙手都進入畫面",
    "Left hand": "左手",
    "Right hand": "右手",
    "Show your {hand}": "請讓{hand}入鏡",
    "{hand} at the edge": "{hand}在畫面邊緣",
    "hold still": "保持不動",
    "{s} s left": "剩 {s} 秒",
    "Keep both hands in the picture": "請讓雙手都留在畫面中",
    "{n} of 2 hands": "偵測到 {n}/2 隻手",
    "Glove IMU": "手套 IMU",

    # ── Results ────────────────────────────────────────────────────────────
    "Hand Tremor - Results": "手部顫抖 — 結果",
    "Strongest rhythm: {phase}, {hand}": "最強節律：{phase}，{hand}",
    "Largest movement in the tremor band (% of hand length)":
        "顫抖頻段中最大的動作量（手長的 %）",
    "Palms up": "掌心朝上",
    "Palms down": "掌心朝下",
    "Arms out": "平舉",
    "Glove sensor at rest: {hz} Hz": "手套感測器（靜止）：{hz} Hz",

    # ── Bands + failure states (core/tremor/metrics.py) ────────────────────
    "Tremor detected - consider follow-up": "偵測到顫抖 — 建議追蹤檢查",
    "No rhythmic shaking found": "沒有發現規律的抖動",
    "A weak rhythm - repeat to confirm": "微弱的節律 — 請重做一次確認",
    "Rhythmic shaking found": "發現規律的抖動",
    "A supporting check for the tapping and spiral tests. Size is an estimate.":
        "點擊與螺旋測驗的輔助檢查。幅度為估計值。",
    "Possible tremor - repeat to confirm": "可能有顫抖 — 請重做一次確認",
    "No tremor detected": "未偵測到顫抖",
    "The camera frame rate was too low to see tremor - close other programs and try again.":
        "鏡頭影格率太低，看不出顫抖 — 請關閉其他程式後再試一次。",
    "The hands kept moving, so there was no still stretch to measure - let them rest and try again.":
        "雙手一直在動，沒有可量測的靜止片段 — 請讓雙手放鬆後再試一次。",
    "Neither hand stayed in view long enough to measure - keep both hands inside the picture.":
        "兩隻手留在畫面中的時間都不夠長，無法量測 — 請讓雙手都留在畫面中。",
    "No hands were detected - check the camera can see both hands, then try again.":
        "沒有偵測到手 — 請確認鏡頭看得到雙手後再試一次。",

    # ── Confidence reasons (core/tremor/confidence.py) ─────────────────────
    "Some parts of the test could not be measured for one or both hands.":
        "有些部分無法量測到一隻或兩隻手。",
    "The hands were in view for only part of each hold.":
        "每段姿勢中，雙手只有部分時間在畫面裡。",
    "Measuring every frame": "正在分析每一格畫面",
    "Sensor glove connected - which hand is wearing it?": "已連接感測手套 — 戴在哪一隻手？",
    "You can rest your hands.": "雙手可以休息了。",
    "Saving the recording": "正在儲存錄影",
    "Recording saved": "錄影已儲存",
    "The results are being measured in the background.": "結果正在背景中分析。",
    "They will appear in the hub in about a minute.": "約一分鐘後會出現在 Hub 中。",
    "This window closes in {n} s": "此視窗將在 {n} 秒後關閉",
    "Close": "關閉",
    "The camera lost frames during the holds.": "錄影時鏡頭掉了一些畫面。",
    "The hands moved during the holds, so parts of the recording were left out.":
        "姿勢維持期間手有移動，所以部分錄製內容被排除。",
    "A hand was often at the edge of the picture.": "手常常位於畫面邊緣。",
    "Part of this reading comes from hand landmarks, which are less precise than the motion tracking.":
        "部分結果來自手部關鍵點，準確度不如動作追蹤。",

    # ══ Hand-tracking inspector ════════════════════════════════════════════
    "{name} hand": "{name}手",
    "Left": "左",
    "Right": "右",
    "Closed": "合攏",
    "Open": "張開",
    "Dist": "距離",
    "Landmark Coordinates": "特徵點座標",
    "Wrist": "手腕",
    "Thumb": "拇指",
    "Index": "食指",
    "Middle": "中指",
    "Ring": "無名指",
    "Pinky": "小指",

    # ══ Camera mirroring check (core/mirror_check.py) ═════════════════════
    "Camera check": "相機檢查",
    "Raise your right hand beside your face": "請把右手舉到臉旁",
    "Show your face to the camera": "請讓臉部入鏡",
    "Use your right hand, palm to the camera": "請用右手，掌心朝向鏡頭",
    "Picture is mirrored. It will be corrected": "畫面是鏡像的，將自動修正",
    "Picture is not mirrored": "畫面不是鏡像的",
    "Checked once per camera. Press Q to skip": "每台相機只需檢查一次。按 Q 略過",
    "Show one hand only": "只讓一隻手入鏡",
    "Camera mirroring check could not run: {error}": "無法執行相機鏡像檢查：{error}",
    "Camera mirroring check skipped - frames are used as the camera sends them. "
    "It will be asked again next launch.":
        "已略過相機鏡像檢查，畫面維持相機原樣。下次啟動時會再詢問",
    "Could not save the mirroring answer; it will be asked again next launch.":
        "無法儲存鏡像檢查結果，下次啟動時會再詢問",
    "Camera picture is mirrored - corrected.": "相機畫面是鏡像的，已自動修正",
    "Camera picture is not mirrored.": "相機畫面不是鏡像的",

    # ══ Console (phase 3: core/splash.py, core/camera.py, entry scripts) ══
    # Printed through i18n.ct(), which keeps English on a console that cannot
    # show CJK. Stage names that are product names (OpenCV, MediaPipe) stay Latin.
    "Modes: Big & Fast (primary) / Paced Rhythm":
        "模式：大動作快速敲擊（主要）／節拍同步敲擊",
    "Eye Movement Test (Pro/Anti-saccade)": "眼球運動測驗（順向／反向掃視）",
    "Part 1: look toward - Part 2: look away - Part 3: hold still":
        "第一部分：看向光點　第二部分：看向反方向　第三部分：保持不動",
    "Parts: Pa-Ta-Ka / Sustained Ahh": "兩部分：Pa-Ta-Ka 交替音節／持續發「啊」",
    "Click 'Start Test' in the camera window.  Q to quit.":
        "請在相機視窗中按「開始測驗」。按 Q 離開",
    "Hand Detection 3D - Data Inspector": "Hand Detection 3D － 資料檢視器",
    "Live landmark inspector + UDP broadcast": "即時關鍵點檢視＋UDP 廣播",
    "Test engine": "測驗引擎",
    "Gaze engine + MediaPipe": "視線引擎＋MediaPipe",
    "Audio engine": "音訊引擎",
    "Loading {what}...": "正在載入 {what}…",
    "Ready": "準備完成",
    "{note} in {secs} s": "{note}，用時 {secs} 秒",
    "First launch reads ~130 MB of vision libraries from disk.":
        "首次啟動需從磁碟讀取約 130 MB 的視覺函式庫",
    "Slow cold start - see docs/performance/COLD_START.md to speed it up.":
        "冷啟動較慢，加速方法見 docs/performance/COLD_START.md",
    "webcam {n}": "網路攝影機 {n}",
    "Press Enter to close...": "按 Enter 關閉…",
    "Camera source: {source}  (set in the launcher)": "相機來源：{source}（於控制台設定）",
    "Camera source:": "相機來源：",
    "Webcam (default)  - or type an index, e.g. 0 / 1 / 2":
        "網路攝影機（預設），或輸入編號，例如 0 / 1 / 2",
    "IP stream URL": "IP 串流網址",
    "Select [1]: ": "請選擇 [1]：",
    "Stream URL: ": "串流網址：",
    "Opening camera and loading the hand model - a few seconds...":
        "正在開啟相機並載入手部模型，約需數秒…",
    "Opening camera and loading the face model - a few seconds...":
        "正在開啟相機並載入臉部模型，約需數秒…",
    "Could not open camera.": "無法開啟相機",
    "Finger tapping test closed.": "手指敲擊測驗已關閉",
    "Spiral tracing test closed.": "螺旋描繪測驗已關閉",
    "Hand tremor test closed.": "手部顫抖測驗已關閉",
    "Eye movement test closed.": "眼球運動測驗已關閉",
    "Speech test closed.": "說話測驗已關閉",

    # ── Walking test, seated part (screening_tests/gait_test.py, core/gait)
    "Walking test closed.": "行走測驗已關閉",
    "Opening camera and loading the pose model - a few seconds...":
        "正在開啟相機並載入姿勢模型，約需數秒…",
    "Walking Test": "行走測驗",
    "Walking Test - Results": "行走測驗－結果",
    "Seated part: leg stamps and five sit-to-stands.":
        "坐姿部分：踏腳與五次坐站。",
    "Use a sturdy chair. Have someone with you.":
        "請使用穩固的椅子，並有人在旁陪同。",
    "Camera side-on, 2-3 m away, whole body in view.":
        "相機放在側面，距離 2-3 公尺，全身入鏡。",
    "Your helper presses Space to move on.": "由陪同者按空白鍵繼續。",
    "Sit so your whole body is in view": "坐好，讓全身都在畫面中",
    "Side-on to the camera, feet included.": "側身面向相機，雙腳也要入鏡。",
    "Raise your right arm above your head": "請把右手舉過頭頂",
    "This tells the test which side is which.": "這讓測驗分辨左右。",
    "hold it up": "保持舉起",
    "Skip this check": "略過此檢查",
    "Press Space when ready.": "準備好後請按空白鍵。",
    "Sit still": "請坐著不動",
    "{n} stamps": "{n} 次踏腳",
    "{n} of {total} stands": "第 {n}／{total} 次站起",
    "Stay in the picture": "請留在畫面中",
    "Five sit-to-stands": "五次坐站",
    "{hz} stamps/s, lift {amp}%": "每秒 {hz} 次，抬高 {amp}%",
    "Right leg": "右腳",
    "Left leg": "左腳",
    "Rises": "站起",
    "{n} stands, {f} failed, hands used {u}":
        "站起 {n} 次，失敗 {f} 次，用手 {u} 次",
    "Left vs right": "左右比較",
    "{leg} weaker": "{leg}較弱",
    "No clear difference": "無明顯差異",
    "No one in view": "畫面中沒有人",
    "Body at the edge": "身體在畫面邊緣",
    "Body in view": "身體在畫面中",
    "Sides checked": "已確認左右",
    "Move the camera back so your feet are in view":
        "請把相機往後移，讓雙腳入鏡",
    "Move the camera back so your head is in view":
        "請把相機往後移，讓頭部入鏡",
    "Move toward the middle of the picture": "請往畫面中間移動",
    "Right Leg Stamps": "右腳踏腳",
    "Left Leg Stamps": "左腳踏腳",
    "Five Sit-to-Stands": "五次坐站",
    "Stamp your right foot, high and fast": "右腳抬高並快速踏下",
    "Stamp your left foot, high and fast": "左腳抬高並快速踏下",
    "Stand up and sit down, five times": "站起再坐下，共五次",
    "gait.leg_right.instructions": [
        "坐好靠著椅背。",
        "把右腳盡量抬高，",
        "再用力踏下，反覆進行，",
        "越快越好。左腳保持不動。",
    ],
    "gait.leg_left.instructions": [
        "現在換另一隻腳。",
        "把左腳盡量抬高，",
        "再用力踏下，反覆進行，",
        "越快越好。右腳保持不動。",
    ],
    "gait.sts5.instructions": [
        "雙臂交叉放在胸前。",
        "聽到嗶聲後，完全站起再坐下，",
        "共五次，在安全的前提下越快越好。",
        "需要時可以用手扶。",
    ],
    "Too few stamps were seen to score this leg.":
        "偵測到的踏腳次數太少，無法評分這隻腳。",
    "The leg was out of view for too much of the block.":
        "這段測驗中，腳有太多時間不在畫面內。",
    "No stand was seen - check that your hips and knees are in view.":
        "沒有偵測到站起，請確認髖部與膝蓋都在畫面中。",
    "The sit-to-stand part could not be measured.": "坐站部分無法測量。",
    "Did not finish five stands": "未完成五次站起",
    "Slower than typical - consider monitoring": "比一般慢，建議持續觀察",
    "Slow to rise - recommend follow-up": "站起緩慢，建議進一步檢查",
    "Parts of your body were often out of the picture.":
        "身體有部分常常不在畫面中。",
    "Some parts of the test could not be measured.": "測驗有部分無法測量。",
    "Left and right were not confirmed, so the legs may be swapped.":
        "左右未經確認，兩腳的結果可能對調。",
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
    # sustained phonation
    (re.compile(r"^Only (\d+(?:\.\d+)?) s of steady voice was recorded - at "
                r"least (\d+(?:\.\d+)?) s is needed\. Hold the sound for the "
                r"whole countdown\.$"),
     "只錄到 $1 秒的穩定聲音 — 至少需要 $2 秒。請在整個倒數期間持續發聲。"),
    # speech rhythm (DDK)
    (re.compile(r"^Only (\d+) syllables detected - at least (\d+) are needed "
                r"for a reliable score\.$"),
     "只偵測到 $1 個音節 — 可靠的評分至少需要 $2 個。"),
    (re.compile(r"^Speech was too slow to score a rhythm "
                r"\((\d+(?:\.\d+)?) syllables/s\)\. Keep repeating without "
                r"pausing between syllables\.$"),
     "說話速度太慢，無法評估節奏（每秒 $1 個音節）。請連續重複，音節之間不要停頓。"),
    # oculomotor
    (re.compile(r"^Only (\d+) valid anti-saccade trials - at least (\d+) "
                r"are needed for a reliable score\.$"),
     "只有 $1 次有效的反向掃視試次 — 可靠的評分至少需要 $2 次。"),
)
