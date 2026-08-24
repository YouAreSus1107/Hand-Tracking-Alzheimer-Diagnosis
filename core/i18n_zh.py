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

Covered so far: the shared UI toolkit and the finger-tapping test (phase 1 of
docs/OVERLAY_I18N_PLAN.md). Spiral and oculomotor land in phase 2.
"""

import re

ZH: dict[str, object] = {

    # ── Shared UI toolkit (core/ui) ────────────────────────────────────────
    "Motor Screening": "動作篩檢",
    "Screening tool, not a diagnosis - consult a healthcare professional.":
        "此為篩檢工具，並非診斷結果 — 請諮詢醫療專業人員。",

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
        "完全張開、完全合攏 — 持續 10 秒。",
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
    "Not enough valid intervals to compute variability.":
        "有效的間隔數量不足，無法計算變異度。",
}


# Strings the engine formatted before storing them. `$1` takes group 1.
ZH_RULES = (
    (re.compile(r"^Only (\d+) taps detected - at least (\d+) are needed "
                r"for a reliable score\.$"),
     "只偵測到 $1 次敲擊 — 可靠的評分至少需要 $2 次。"),
)
