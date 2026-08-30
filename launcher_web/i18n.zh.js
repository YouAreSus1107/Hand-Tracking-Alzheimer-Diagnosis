/* ── 繁體中文 dictionary ──────────────────────────────────────────────
   Chinese only. English lives where it already lived — in index.html and in
   the JS source strings — so there is exactly one copy of it and anything
   missing here falls back to English instead of showing a raw key.

   Two kinds of key:
     "page.thing"   dotted  → a data-i18n block in index.html; the value keeps
                             the same inline markup (links, <strong>, <code>)
     "Launch"       English → a string rendered from app.js / dev.js

   House style (agreed with Adam): translate the prose, keep the term. Metric
   acronyms (CV%, SPARC, SMD), identifiers, file paths, citations and author
   names stay Latin — they are what you search for and what the papers use. */

window.ZH = {

/* ── shared ─────────────────────────────────────────────────────────── */
"common.howItWorks": `運作方式`,
"common.metrics": `量測指標`,
"common.papers": `研究論文`,
"common.readPaper": `閱讀論文`,
"common.tag.oneHand": `單手`,

/* ── chrome ─────────────────────────────────────────────────────────── */
"doc.title": `認知篩檢套件 &#8212; 控制中心`,
"nav.logo.aria": `前往主控台`,
"nav.logoText": `認知篩檢套件`,
"nav.home": `主控台`,
"nav.why": `差異比較`,
"nav.analysis": `趨勢分析`,
"nav.remote": `遠端測驗`,
"nav.iiv": `手指敲擊`,
"nav.spiral": `螺旋描繪`,
"nav.oculomotor": `眼球運動`,
"nav.tracking": `手部追蹤`,
"nav.dev": `開發者`,
"nav.tests": `測驗`,
"nav.about": `關於`,
"nav.aboutMe": `關於我`,

/* About me (placeholder page) */
"about.h1": `關於我`,
"about.intro": `目前還沒有內容。`,
"bar.disclaimer": `篩檢工具，<strong>並非正式醫療診斷</strong> &#8212; 請諮詢專業醫療人員。
  &#160;&#183;&#160;
`,

/* ── dashboard ──────────────────────────────────────────────────────── */
"home.h1": `以相機進行的<br><span class="grad">認知篩檢</span>`,
"home.sub": `由 Adam Chung 製作。`,
"home.sec.vitals": `你的測量結果`,
"home.vitals.link": `完整趨勢 &#8594;`,
"home.sec.tools": `篩檢工具`,
"home.warn": `&#9888;&#160;請關閉無關程式以釋出 CPU`,
"home.warn.title": `相機測驗會在 CPU 上執行大量即時視覺運算。關閉背景程式可釋出核心，讓影格率維持在 30 fps 以上。`,
"home.carousel.aria": `篩檢工具`,
"home.carousel.prev": `上一個工具`,
"home.carousel.next": `下一個工具`,
"home.carousel.dots": `選擇工具`,
"home.sec.research": `研究依據`,
/* ── hub connection panel (published site only; tools/web_static/static-api.js) ──
   Prose is translated, the machine words are not: run_hub.bat, setup.bat and
   127.0.0.1:8770 stay Latin, and {addr} is the placeholder the connector fills
   with the hub's address. */
"get.eyebrow": `本機 Hub`,
"get.h": `在您自己的電腦上執行測驗`,
"get.lead": `篩檢測驗以 Python 撰寫並需要使用相機，因此在您的電腦上執行 &#8212;
  本頁只負責操作它們。安裝一次之後，這裡的每個按鈕都會生效。`,
"get.s1.h": `下載`,
"get.s1.p": `安裝包，8&#160;MB。`,
"get.s1.tip": `Windows &#183; Python 3.9&#8211;3.12`,
"get.s2.h": `安裝`,
"get.s2.p": `解壓縮到任意位置，執行一次 <code>setup.bat</code>。`,
"get.s2.tip": `它會建立執行環境並下載模型`,
"get.s3.h": `連線`,
"get.s3.p": `執行 <code>run_hub.bat</code> 後回到本頁。`,
"get.s3.tip": `頁面會自動找到它 &#8212; 不需輸入任何內容`,
/* the two steps already behind you, and the captions inside the artwork */
"get.chip.dl": `已下載`,
"get.chip.install": `已安裝`,
"get.art.page": `本頁`,
"get.art.machine": `您的電腦`,
"get.dl": `下載 Windows 版`,
"get.connect": `連接本頁`,
"get.connect.tip": `向 Hub 索取配對碼並交給本頁`,
"get.connect.locked": `請先在您的電腦上啟動 Hub`,
"get.recheck": `重新偵測`,
"get.listen": `正在偵測 <code>127.0.0.1:8770</code> 上的 Hub &#8212; 已經安裝了嗎？請執行 <code>run_hub.bat</code>。`,
"get.retry": `再試一次`,
"get.state.probing": `偵測中&#8230;`,
"get.state.offline": `尚未連線`,
"get.state.unpaired": `已找到 Hub`,
"get.state.connected": `已連線`,
"get.err.unreachable": `無法連上 <code>{addr}</code> 上的 Hub，它可能已經停止 &#8212;
  請在您的電腦上啟動 <code>run_hub.bat</code>，然後再試一次。`,
"get.err.badcode": `這組配對碼未被接受。請從 Hub 主控台重新複製一次。`,
"get.err.blocked": `您的瀏覽器封鎖了本頁連線至 <code>{addr}</code>。
  Chrome 會先徵求同意，才允許網站與您自己的電腦通訊 &#8212; 出現詢問時請選擇
  <strong>允許</strong>，或在網址列旁的鎖頭選單中為本網站開啟
  <strong>區域網路存取</strong>，然後再試一次。`,
"get.err.maybeblocked": `如果它已經在執行中，可能是瀏覽器尚未授予存取您電腦的權限 &#8212;
  出現詢問時請選擇 <strong>允許</strong>，或在網址列旁的鎖頭選單中為本網站開啟
  <strong>區域網路存取</strong>。`,
"get.toast.connected": `已連上這台電腦上的 Hub。`,
"get.toast.found": `已找到 Hub，請連接本頁以完成配對。`,
"get.toast.nohub": `{addr} 上仍然沒有 Hub 回應。`,
"get.toast.blocked": `仍然被封鎖。請在鎖頭選單中為本網站開啟區域網路存取。`,
"get.msg.nohub": `{addr} 上沒有 Hub 回應 &#8212; 請在您的電腦上執行 run_hub.bat。`,
"get.msg.blocked": `您的瀏覽器封鎖了本頁連線至 {addr} 上的 Hub。`,
"get.msg.pairfirst": `請先將本頁與您的 Hub 配對。`,
"get.note": `需要 Windows 與 Python 3.9&#8211;3.12，並使用 Chrome 或 Edge。Safari 會封鎖
  https 頁面存取本機 Hub。您錄下的資料不會上傳：本頁只與您的電腦通訊，不會送到伺服器。`,
"get.manual.sum": `手動配對`,
"get.manual": `或貼上 Hub 主控台顯示的配對碼：`,
"get.pair": `配對`,
"get.forget": `清除已儲存的配對碼`,
"get.chip": `Hub`,
"get.chip.title": `已配對的 Hub`,
"get.chip.addr": `位址`,
"get.chip.ver": `版本`,
/* hand model state label (hand3d.js) */
"anatomical": `解剖模型`,
"digitalized": `數位化`,
"morphing…": `變形中…`,
"home.footer": `本機服務 &#183; 127.0.0.1 &#183; 資料不會離開這台電腦 &#183;
      <a href="/analysis" target="_blank">完整研究分析</a>
    `,

/* ── longitudinal analysis ──────────────────────────────────────────── */
"analysis.h1": `縱向趨勢分析`,
"analysis.intro": `長期趨勢比任何單次結果更重要。所有資料都留在這台電腦上。`,
"analysis.filter.aria": `依測驗篩選`,
"analysis.disclaimer": `參考區間為<strong>暫定值</strong>，只為圖表提供背景參考 &#8212;
        並非臨床切點。本套件是篩檢輔助，不是診斷。
      `,

/* ── why this ───────────────────────────────────────────────────────── */
"why.h1": `與其他工具的比較`,
"why.intro": `居家認知篩檢工具多半不是自填問卷，就是無法檢視內部的封閉研究平台。
            這一套在本機執行，會標示每項指標背後的論文，並保留歷次紀錄。
            搭配相機量測握力的感測手套仍在開發中。`,
"why.sec.pillars": `差異所在`,
"why.sec.matrix": `逐項比較`,
"why.disclaimer": `這是<strong>篩檢輔助，不是診斷</strong>。在建立常模樣本之前，
        評分區間都是暫定值；於病患族群上的效度驗證是路線圖中決定性的下一步
        &#8212; 上表已如實標示。
      `,

/* ── finger tapping ─────────────────────────────────────────────────── */
"iiv.h1": `手指敲擊測驗`,
"iiv.lede": `用食指有節奏地敲擊拇指。`,
"iiv.tag1": `大幅快速（20 秒）`,
"iiv.tag2": `跟拍節奏（30 秒）`,
"iiv.tag4": `主要指標 CV%`,
"iiv.how.intro": `兩種模式共用同一套偵測引擎，校正流程也相同，差別只在敲擊的節奏由誰決定。`,
"iiv.mode1.h": `大幅快速`,
"iiv.mode1.badge": `20 秒 &#183; 自訂節奏 &#183; 主要模式`,
"iiv.mode1.s1.h": `校正`,
"iiv.mode1.s1.p": `選擇網路攝影機或 IP 攝影機。MediaPipe 會追蹤手上的 21 個點；先做一次張開合攏的暖身，依你的手掌大小設定起始的敲擊門檻，之後門檻會跟著你實際的動作幅度調整 — 幅度變小時仍能被計入。`,
"iiv.mode1.s2.h": `又大又快地敲`,
"iiv.mode1.s2.p": `用食指敲擊拇指，<strong>在 20 秒內盡可能敲得又大又快</strong>。程式會逐格量測指尖之間的距離。我們的實測結果約為每秒 1 至 2 下；TapTalk 在相同指示下測得每秒 5 至 7 下，這個差距目前尚未釐清。`,
"iiv.mode1.s3.h": `評分`,
"iiv.mode1.s3.p": `主要分數是敲擊間隔的 <strong>CV%</strong>。另外還會得到敲擊頻率、幅度變異度與速度衰減。`,
"iiv.mode2.h": `跟拍節奏`,
"iiv.mode2.badge": `30 秒 &#183; 1 Hz 節拍器`,
"iiv.mode2.s1.h": `校正`,
"iiv.mode2.s1.p": `相機設定與張開合攏的暖身完全相同，用來設定你的敲擊門檻。`,
"iiv.mode2.s2.h": `跟著節拍暖身`,
"iiv.mode2.s2.p": `會有 5 秒跟著節拍器練習。嗶聲<strong>提前 200 毫秒</strong>播放以抵消音訊延遲，並排在固定的時間格上，因此不會逐漸偏移。`,
"iiv.mode2.s3.h": `每聲嗶敲一下`,
"iiv.mode2.s3.p": `<strong>每一聲嗶敲一下</strong>，持續 30 秒，每秒一聲。保持穩定比完全準時更重要。`,
"iiv.mode2.s4.h": `評分`,
"iiv.mode2.s4.p": `主要分數是 <strong>CV%</strong>，也就是節奏一致性。<strong>節拍同步 SD</strong> 顯示敲擊落點與嗶聲的接近程度。前 3 下暖身敲擊不計入。`,
"iiv.m1.h": `節奏變異度（CV%）`,
"iiv.m1.p": `測驗記錄敲擊間隔的標準差，是不受尺度影響的主要生物標記。`,
"iiv.m1.num": `&lt;15% 一般 &#183; 15&#8211;25% 觀察 &#183; &gt;25% 建議追蹤*`,
"iiv.m1.cite": `多個神經退化族群的 IIV 皆升高 &#8212; <a href="https://pmc.ncbi.nlm.nih.gov/articles/PMC5992087/" target="_blank" rel="noopener">Roalf 2018</a>, <a href="https://pmc.ncbi.nlm.nih.gov/articles/PMC11496774/" target="_blank" rel="noopener">TapTalk 2024</a>`,
"iiv.m2.h": `敲擊頻率（Hz）`,
"iiv.m2.p": `每秒敲擊次數 = 1000 &#247; 平均敲擊間隔。`,
"iiv.m2.num": `大幅快速模式在完全張開合攏下約為 1&#8211;2 Hz`,
"iiv.m2.cite": `MediaPipe 測得的頻率有 90.3% 落在 Polhemus 感測器的 &#177;1 Hz 內 &#8212; <a href="https://pmc.ncbi.nlm.nih.gov/articles/PMC11496774/" target="_blank" rel="noopener">TapTalk 2024</a>。同一篇研究測得 5&#8211;7 Hz，而我們為 1&#8211;2 Hz；差距尚未釐清。`,
"iiv.m3.h": `速度衰減（%/秒）`,
"iiv.m3.p": `整段測驗中瞬時敲擊速率的斜率，用來捕捉疲勞造成的變慢。`,
"iiv.m3.num": `負值 = 變慢`,
"iiv.m3.cite": `「大幅快速」衰減指標 &#8212; <a href="https://pmc.ncbi.nlm.nih.gov/articles/PMC11496774/" target="_blank" rel="noopener">TapTalk 2024</a>`,
"iiv.m4.h": `幅度 CV（%）`,
"iiv.m4.p": `每次敲擊由最低點到最高點的張開幅度，其變異程度。`,
"iiv.m4.num": `以每次敲擊的幅度標準化`,
"iiv.m4.cite": `磁感測器的敲擊幅度／規律性 &#8212; <a href="https://pmc.ncbi.nlm.nih.gov/articles/PMC9716461/" target="_blank" rel="noopener">Suzumura 2022</a>`,
"iiv.m5.h": `節拍同步 SD（毫秒）&#183; 僅跟拍模式`,
"iiv.m5.p": `每次敲擊與最接近嗶聲之間延遲的標準差（在 &#177;500 毫秒視窗內配對）。`,
"iiv.m5.num": `數值越低代表越貼合節拍`,
"iiv.m5.cite": `本專案自訂的節奏指標 &#8212; 無引用的常模來源。`,
"iiv.note": `至少需要 6 次敲擊；每次結果都會附上信賴程度。<strong>*15% 與 25% 的切點是本專案自訂，並非文獻數值</strong> — 尚無常模資料。僅供參考，不是診斷。`,
"iiv.p1.title": `<a href="https://pmc.ncbi.nlm.nih.gov/articles/PMC5992087/" target="_blank" rel="noopener">輕度認知障礙、阿茲海默症與帕金森氏症的量化手指敲擊</a>`,
"iiv.p1.authors": `Roalf 等，2018 &#183; J Neurol 265:1365&#8211;1375 &#183; PMC5992087`,
"iiv.p1.body": `研究以光二極體敲擊器測試 302 人（131 位 AD、63 位 PD、46 位 MCI、62 位健康對照）。所有神經退化族群的敲擊間隔變異都較高，且比敲擊次數或平均速度更能區分族群。我們引用它，是因為主要指標 <strong>CV% / IIV</strong> 出自此研究。`,
"iiv.p1.tag": `我們 IIV／CV 指標的來源`,
"iiv.p2.title": `<a href="https://pmc.ncbi.nlm.nih.gov/articles/PMC11496774/" target="_blank" rel="noopener">TapTalk：橫跨 20 款裝置的手機動作與語音測試</a>`,
"iiv.p2.authors": `Li 等，2024 &#183; Alzheimer's &amp; Dementia: DADM &#183; PMC11496774`,
"iiv.p2.body": `研究在 31 位受試者、20 款手機上，把 MediaPipe 手部追蹤與 Polhemus 電磁感測器對照。90.3% 的敲擊頻率讀值落在感測器的 &#177;1 Hz 內。我們引用它，是因為它證明一般相機的精度足以進行這項測驗。`,
"iiv.p2.tag": `直接驗證我們的做法`,
"iiv.p3.title": `<a href="https://pmc.ncbi.nlm.nih.gov/articles/PMC10809289/" target="_blank" rel="noopener">TAS Test：網路攝影機手部動作可預測認知功能</a>`,
"iiv.p3.authors": `Li 等，2024 &#183; Alzheimer's &amp; Dementia: DADM &#183; PMC10809289`,
"iiv.p3.body": `404 位沒有認知症狀的成人在家完成 10 秒的網路攝影機敲擊測驗。加入手部動作特徵後，對記憶、執行功能與工作記憶的預測都變好。我們引用它，是因為它證明這項測驗在家中無人監督也能運作。`,
"iiv.p3.tag": `居家網路攝影機驗證`,

/* ── spiral tracing ─────────────────────────────────────────────────── */
"spiral.h1": `螺旋描繪測驗`,
"spiral.lede": `用指尖在空中描繪螺旋。`,
"spiral.tag1": `40 秒測驗`,
"spiral.tag3": `螢幕導引`,
"spiral.tag4": `空中描繪`,
"spiral.s1.h": `顯示導引`,
"spiral.s1.p": `螢幕上會出現螺旋導引線。把手舉在相機前方，並伸出食指。`,
"spiral.s2.h": `描繪螺旋`,
"spiral.s2.p": `用指尖從中心往外描繪螺旋，速度以自己覺得舒適為準。畫面上沒有需要追逐的圓點。程式會逐格記錄未經平滑的指尖位置。`,
"spiral.s3.h": `動作分析`,
"spiral.s3.p": `程式會檢視描繪過程中速度的變化，評估動作有多平滑穩定，而不是你和目標線貼合的程度。`,
"spiral.s4.h": `平滑度評分`,
"spiral.s4.p": `主要分數是名為 <strong>SPARC</strong> 的平滑度指數。另外還會得到速度 CV%、標準化急動度、震顫讀值，以及螺旋完成比例。`,
"spiral.m1.h": `平滑度指數（SPARC）`,
"spiral.m1.p": `速度曲線的頻譜弧長（Balasubramanian 等，2015），對應到 0&#8211;100。主要指標：數值越高代表動作越平滑、越自動化。`,
"spiral.m2.h": `速度 CV%`,
"spiral.m2.p": `動作速度的變異係數。速度曲線不規則是神經退化的典型特徵。`,
"spiral.m3.h": `標準化急動度`,
"spiral.m3.p": `動作軌跡的平滑程度。動作越急促，代表動作自動化程度越低。`,
"spiral.m4.h": `完成度`,
"spiral.m4.p": `成功描繪的螺旋比例。完成度偏低可能代表動作疲勞或困難。`,
"spiral.m5.h": `活動比例`,
"spiral.m5.p": `手指實際移動與停頓時間的比例。猶豫停頓可能代表動作規劃困難。`,
"spiral.p1.title": `數位化阿基米德螺旋描繪測驗 &#8212; 範疇回顧`,
"spiral.p1.authors": `Wang 等，2025 &#183; Movement Disorders Clinical Practice`,
"spiral.p1.body": `回顧數位螺旋測驗在多發性硬化症、共濟失調、肌張力不全、小腦疾病、MCI 與阿茲海默症中的應用。我們引用它，是因為它確認螺旋描繪是成熟且可量化的測驗。`,
"spiral.p1.tag": `佐證測驗方向`,
"spiral.p2.title": `以可解釋 CNN 從螺旋與波形描繪判別帕金森氏症`,
"spiral.p2.authors": `2024/2025 &#183; Springer`,
"spiral.p2.body": `深度學習模型從螺旋與波形描繪判別帕金森氏症，其顯著圖會標示是哪些部分促成判斷。我們引用它，作為自動評分仍可保持可解釋的範例。`,
"spiral.p2.tag": `可解釋 AI 做法`,
"spiral.p3.title": `結合敲擊與螺旋的震顫鑑別診斷`,
"spiral.p3.authors": `NCT06378619 &#183; ClinicalTrials.gov`,
"spiral.p3.body": `一項進行中的試驗，結合敲擊與螺旋描繪並以機器學習區分震顫類型。我們引用它，作為把本套件各項測驗合併成單一分類器的先例。`,
"spiral.p3.tag": `合併測驗的先例`,

/* ── eye movement ───────────────────────────────────────────────────── */
"oculo.h1": `眼球運動測驗`,
"oculo.lede": `只用網路攝影機的<strong>順向／反向掃視</strong>作業。畫面左右會閃出一個圓點：
          第 1 部分請<strong>看向</strong>它，第 2 部分請<strong>看向反方向</strong>。
          主要指標是<strong>反向掃視錯誤率</strong>，也就是眼睛仍被圓點吸引過去的比例。
          它量測的是抑制控制，是目前可量測的阿茲海默症最早期徵象之一。`,
"oculo.tag1": `順向基準（16 試次）`,
"oculo.tag2": `反向掃視（24 試次）`,
"oculo.tag3": `三點注視校正`,
"oculo.tag4": `主要指標為錯誤率`,
"oculo.how.intro": `兩個區段共用同一套視線引擎。MediaPipe 會追蹤虹膜，並以眼角為基準量測它的位置，因此輕微的頭部移動不會影響結果。短暫的校正把這個訊號對應到螢幕位置。`,
"oculo.s1.h": `校正`,
"oculo.s1.p": `依序注視三個圓點：中央、左、右。這會把虹膜訊號對應到螢幕位置，並依你自己的追蹤雜訊設定中央<strong>死區</strong>。請保持頭部不動，只移動眼睛。`,
"oculo.s2.h": `第 1 部分 &#8212; 看向圓點`,
"oculo.s2.p": `眼睛注視中央十字。圓點出現時<strong>看向</strong>它，再看回中央。16 個計分試次會建立你正常掃視速度的基準。`,
"oculo.s3.h": `第 2 部分 &#8212; 看向反方向`,
"oculo.s3.p": `圓點出現時，看向<strong>相反</strong>的一側。這是主要區段，24 個試次量測抑制失敗的頻率，以及正確注視的速度。`,
"oculo.s4.h": `評分`,
"oculo.s4.p": `主要分數是<strong>反向掃視錯誤率</strong>。<strong>反向 &#8722; 順向潛伏期</strong>抵消相機與顯示器的固定延遲。另外還有已修正錯誤率與資料品質檢查。兩個區段都採用<strong>間隔範式</strong>，並排除快於 90 毫秒的猜測反應。`,
"oculo.m1.h": `反向掃視錯誤率（%）`,
"oculo.m1.p": `第一個眼動方向朝向圓點的反向掃視試次比例 &#8212; 代表抑制失敗。`,
"oculo.m1.num": `&lt;20% 一般 &#183; 20&#8211;40% 觀察 &#183; &gt;40% 建議追蹤*`,
"oculo.m1.cite": `對 AD 區辨力最佳（SMD 1.59）&#8212; <a href="https://pmc.ncbi.nlm.nih.gov/articles/PMC9090874/" target="_blank" rel="noopener">Opwonya 2022</a>`,
"oculo.m2.h": `反向 &#8722; 順向潛伏期（毫秒）`,
"oculo.m2.p": `反向掃視潛伏期減去順向掃視基準。相減可抵消相機曝光與畫面繪製造成的固定未知延遲。`,
"oculo.m2.num": `較穩健的潛伏期讀值`,
"oculo.m2.cite": `標準化實驗流程 &#8212; <a href="https://pubmed.ncbi.nlm.nih.gov/23474300/" target="_blank" rel="noopener">Antoniades 2013</a>`,
"oculo.m3.h": `已修正錯誤率（%）`,
"oculo.m3.p": `反向掃視錯誤中，眼睛在維持視窗內自行修正到正確一側的比例 &#8212; 區分抑制失敗與錯誤監控。`,
"oculo.m3.num": `分開計算`,
"oculo.m3.cite": `已修正與未修正錯誤 &#8212; <a href="https://pubmed.ncbi.nlm.nih.gov/15860346/" target="_blank" rel="noopener">Crawford 2005</a>`,
"oculo.m4.h": `潛伏期 CV（%）&#183; 效度門檻`,
"oculo.m4.p": `正確試次潛伏期的變異度，加上有效試次數與臉部可見比例，決定一次測驗是否可計分。`,
"oculo.m4.num": `如實呈現資料品質`,
"oculo.m4.cite": `排除快速／預期性（&lt;90 毫秒）掃視。`,
"oculo.note": `一次測驗至少需要 <strong>12 個有效的反向掃視試次</strong>才能計分。這是<strong>簡短篩檢版</strong>（40 試次，臨床版每區段 40&#8211;60 試次）。30&#8211;60 fps 的網路攝影機能穩定判斷掃視<em>方向</em>，但無法量測速度或軌跡。<strong>*區間以已發表的健康者（約 6%）與 AD（約 25%）錯誤率為錨點</strong>（<code>core/gaze/metrics.py</code>）&#8212; 並非臨床切點。表現會受光線、相機品質、眼鏡與專注度影響。`,
"oculo.p1.title": `<a href="https://pmc.ncbi.nlm.nih.gov/articles/PMC9090874/" target="_blank" rel="noopener">輕度認知障礙與阿茲海默症的掃視性眼動 &#8212; 統合分析</a>`,
"oculo.p1.authors": `Opwonya 等，2022 &#183; Neuropsychology Review 32(2):193&#8211;227 &#183; PMC9090874`,
"oculo.p1.body": `匯集 27 組作業條件資料的統合分析。反向掃視錯誤率在區分 AD 與對照組時效果量<strong>大</strong>（SMD 1.59），對 MCI 為中等（0.55），而且在區辨病患與對照上優於順向掃視指標。我們引用它，是因為主要指標出自此研究。`,
"oculo.p1.tag": `我們主要指標的來源`,
"oculo.p2.title": `<a href="https://pubmed.ncbi.nlm.nih.gov/15860346/" target="_blank" rel="noopener">阿茲海默症的掃視抑制控制與認知功能損害</a>`,
"oculo.p2.authors": `Crawford 等，2005 &#183; Biological Psychiatry 57(9):1052&#8211;1060 &#183; PMID 15860346`,
"oculo.p2.body": `AD 患者未修正的反向掃視錯誤約為對照組的 10 倍（平均 25.4%），且錯誤率與失智嚴重度相關。我們引用它，是因為它錨定了評分區間的高端。`,
"oculo.p2.tag": `錨定 AD 錯誤率區間`,
"oculo.p3.title": `<a href="https://pubmed.ncbi.nlm.nih.gov/23474300/" target="_blank" rel="noopener">國際標準化的反向掃視實驗流程</a>`,
"oculo.p3.authors": `Antoniades 等，2013 &#183; Vision Research 84:1&#8211;5 &#183; PMID 23474300`,
"oculo.p3.body": `臨床掃視測驗的參考流程。我們遵循它的規則：先做順向掃視區段、十字消失與圓點出現之間留有間隔、排除快速掃視，並把已修正與未修正錯誤分開計算。`,
"oculo.p3.tag": `我們的量測方法`,

/* ── hand tracking ──────────────────────────────────────────────────── */
"track.h1": `手部追蹤 / UDP 廣播`,
"track.lede": `以 UDP 即時串流全部 21 個手部關鍵點（x、y、z）到
          <code style="color:var(--brand)">127.0.0.1:5052</code>。它原本是為 Unity 的手部鏡射
          接收端而寫，現在則是各項篩檢測驗的原始關鍵點骨幹。`,
"track.tag1": `即時串流`,
"track.tag2": `雙手`,
"track.tag3": `UDP :5052`,
"track.tag4": `21 個關鍵點`,
"track.s1.h": `選擇相機`,
"track.s1.p": `主控台視窗會詢問相機來源。可選擇本機網路攝影機，或貼上 IP 攝影機的串流網址。`,
"track.s2.h": `關鍵點偵測`,
"track.s2.p": `MediaPipe 最多同時偵測 2 隻手，每格畫面回傳每隻手的 21 個 3D 關鍵點。`,
"track.s3.h": `UDP 廣播`,
"track.s3.p": `每格畫面都會把換算成像素的座標打包成 <code style="color:var(--brand)">L:[x1,y1,z1,...]</code> 並以 UDP 送出，偵測到的每隻手各一個封包。`,
"track.s4.h": `即時視覺化`,
"track.s4.p": `OpenCV 視窗會顯示相機畫面，並在上面繪製手部骨架。按 <code style="color:var(--brand)">q</code> 結束。`,
"track.sec.data": `資料輸出`,
"track.d1.h": `21 個關鍵點`,
"track.d1.p": `手腕、拇指（4）、食指（4）、中指（4）、無名指（4）、小指（4）&#8212; 依 MediaPipe 拓樸的完整手部骨架。`,
"track.d2.h": `3D 座標`,
"track.d2.p": `每個關鍵點有 x、y（換算為像素）與 z（相對深度）。x/y 以 One-Euro 濾波平滑，z 保持原始值。`,
"track.d3.h": `UDP 格式`,
"track.d3.p": `以換行分隔的封包：<code>L:[x1,y1,z1,x2,y2,z2,...]</code>，每隻手一個，廣播到 localhost:5052。`,
"track.d4.h": `前處理`,
"track.d4.p": `以 <code>preprocess_for_mediapipe</code> 做 CLAHE 與銳化，改善困難光線下的偵測。`,

/* ── developer (sensor glove) ───────────────────────────────────────── */
"dev.h1": `開發者 &#8212; 感測手套`,
"dev.intro": `手套類比通道的建置工具與即時波形。板子會透過 USB 序列埠串流原始 ADC 資料；
            本頁用來檢查工具鏈、燒錄韌體，並繪出感測器與板載 IMU 實際的狀況。規格：
            <code>docs/GLOVE_FIRMWARE_PLAN.md</code>。`,
"dev.sec.toolchain": `工具鏈`,
"dev.sec.conn": `連線`,
"dev.sec.signal": `即時訊號`,
"dev.scope.aria": `即時感測波形`,
"dev.scope.empty": `未連線 &#8212; 沒有訊號。`,
"dev.sec.motion": `動作 &#8212; 板載 IMU`,
"dev.motion.legend": `加速度計 + 陀螺儀，100 Hz`,
"dev.motion.note": `相機說明手<em>在哪裡</em>，速率約 30 fps，而且只有留在畫面內時才有效。
        IMU 裝在手上，說明<em>手怎麼動</em>，速率 100 Hz，遮蔽或離開畫面都仍然有效
        &#8212; 這正是 4&#8211;12 Hz 震顫頻帶需要的。
        規格：<code>docs/GLOVE_FIRMWARE_PLAN.md</code> &#167;5d。`,
"dev.sec.health": `串流健康度`,
"dev.sec.cmds": `板子指令`,
"dev.sec.console": `序列主控台`,
"dev.disclaimer": `同一時間只有一個程式能占用 COM 埠 &#8212; 連線前請先關閉 Arduino
        序列監控視窗與 <code>press_test.ps1</code>。上傳韌體時會自動釋放本頁的連線。
      `,

/* ══ strings rendered from app.js ══════════════════════════════════════
   Keyed by the English source string. Anything not listed falls back to
   English, so a new string is never a broken key on screen. */

/* tool cards (TOOLS) */
"Finger Tapping Test": `手指敲擊測驗`,
"Spiral Tracing Test": `螺旋描繪測驗`,
"Eye Movement Test": `眼球運動測驗`,
"Hand Tracking / UDP": `手部追蹤 / UDP`,
"30 s test": `30 秒測驗`,
"40 s test": `40 秒測驗`,
"~4 min test": `約 4 分鐘`,
"1 hand": `單手`,
"2 hands": `雙手`,
"Audio metronome": `節拍器音效`,
"Paced tapping": `跟拍敲擊`,
"On-screen guide": `螢幕導引`,
"Air tracing": `空中描繪`,
"Pro + anti-saccade": `順向 + 反向掃視`,
"Webcam gaze": `網路攝影機視線`,
"Error rate headline": `主要指標為錯誤率`,
"Live stream": `即時串流`,
"21 landmarks": `21 個關鍵點`,

/* card + detail actions */
"Back to Dashboard": `返回主控台`,
"Launch": `啟動`,
"Launch Test": `啟動測驗`,
"Stop": `停止`,
"Details": `詳細資訊`,
"Running...": `執行中…`,
"Running — check the camera window": `執行中 — 請查看相機視窗`,
"Launch {name}": `啟動{name}`,
"Stop {name}": `停止{name}`,
"View details for {name}": `檢視{name}的詳細資訊`,
"Tool {n}": `工具 {n}`,
"Launch test": `啟動測驗`,

/* camera-source chip */
"Camera source": `相機來源`,
"Camera the tests will use": `測驗將使用的相機`,
"Webcam": `網路攝影機`,
"Webcam {n}": `網路攝影機 {n}`,
"Webcam index": `攝影機編號`,
"IP stream": `IP 串流`,
"Stream URL": `串流網址`,
"Applies to the next launch.": `於下次啟動時生效。`,

/* ── patient profiles (profiles.js, the chip + the post-run card) ────── */
"analysis.person.aria": `依受測者篩選`,
"Who is being tested": `目前受測者`,
"Who the next test records for": `下一次測驗要記錄給誰`,
"No profile": `未指定受測者`,
"Sessions save unassigned": `紀錄將不指定受測者`,
"Add a person": `新增受測者`,
"Edit": `編輯`,
"Edit person": `編輯受測者`,
"Edit details": `編輯資料`,
"Edit {name}": `編輯 {name}`,
"Name": `姓名`,
"Name or initials": `姓名或縮寫`,
"Sex": `性別`,
"Age": `年齡`,
"age {n}": `{n} 歲`,
"Dominant hand": `慣用手`,
"Female": `女性`,
"Male": `男性`,
"Other": `其他`,
"Not specified": `未填寫`,
"Right-handed": `右撇子`,
"Left-handed": `左撇子`,
"Ambidextrous": `雙手皆可`,
"Back": `返回`,
"Remove": `移除`,
"Confirm removal": `確認移除`,
"Their saved sessions stay, and keep the name they were recorded under.":
  `已儲存的紀錄會保留，並維持當時記錄的姓名。`,

/* the card shown once a run has finished */
"{name} saved": `{name} 已儲存`,
"Recorded for {name}": `已記錄給 {name}`,
"Saved with no profile set.": `儲存時未指定受測者。`,
"Who took this test?": `這次是誰受測？`,
"Keep": `維持`,
"Dismiss": `關閉`,

/* the person filter on the Analysis page and the readings strip */
"All people": `所有人`,
"Unassigned": `未指定`,
"Unassigned sessions": `未指定受測者的紀錄`,
"Recorded with no profile set.": `錄製時未指定受測者。`,
"Removed profile": `已移除的受測者`,
"for {name}": `— {name}`,
"unassigned sessions": `— 未指定受測者的紀錄`,
"Nothing logged for this person yet": `這位受測者還沒有任何紀錄`,
"Set them on the profile chip before you launch a test, or move an existing session to them from its report.":
  `啟動測驗前先在受測者標籤選擇他們，或從報告把既有的紀錄改指定給他們。`,

/* the report panel */
"Belongs to": `所屬受測者`,
"Age at test": `受測時年齡`,
"Save": `儲存`,
"Stop test": `停止測驗`,

/* status pills + toasts */
"Hand model": `手部模型`,
"Face model": `臉部模型`,
"Ready": `就緒`,
"Missing": `缺少`,
"OK": `正常`,
"Done": `完成`,
"Failed": `失敗`,
"Request failed": `要求失敗`,

/* research cards (RESEARCH) */
"Motor — rhythm and movement": `動作 — 節奏與移動`,
"Finger tapping measures how much the gaps between taps vary. That variability is higher in neurodegenerative groups than in controls. Spiral tracing adds movement smoothness (SPARC), speed variation, and normalized jerk.":
  `手指敲擊量測敲擊間隔的變異程度；神經退化族群的變異高於對照組。螺旋描繪再加上動作平滑度（SPARC）、速度變異與標準化急動度。`,
"Roalf et al. (2018) · Wang et al. (2025) · PMC11496774": `Roalf 等（2018）· Wang 等（2025）· PMC11496774`,
"Oculomotor — inhibitory control": `眼動 — 抑制控制`,
"The anti-saccade error rate counts how often the eyes are pulled toward a target you were told to look away from. Meta-analysis puts the effect separating Alzheimer's groups from controls at SMD 1.59.":
  `反向掃視錯誤率統計眼睛被「要求別看」的目標吸引過去的次數。統合分析顯示，區分阿茲海默症族群與對照組的效果量為 SMD 1.59。`,
"Opwonya et al. (2022) · Crawford et al. (2005) · PMC9090874": `Opwonya 等（2022）· Crawford 等（2005）· PMC9090874`,
"Speech — not built yet": `語音 — 尚未建置`,
"Word-finding pauses, flat prosody, and reduced vocabulary are among the earliest reported signs of decline. A microphone-only speech task is the next modality planned here.":
  `找不到詞而停頓、語調平板、詞彙量下降，是文獻中最早出現的衰退徵象。只用麥克風的語音作業是本套件規劃中的下一個模式。`,
"Planned — see docs/ROADMAP.md": `規劃中 — 見 docs/ROADMAP.md`,
"The method works at home": `這套方法在家可行`,
"MediaPipe tapping matched Polhemus electromagnetic sensors within ±1 Hz about 90% of the time, and 404 adults with no symptoms completed unsupervised webcam testing at home. Both studies validate the approach, not this implementation.":
  `MediaPipe 敲擊約有 90% 的讀值落在 Polhemus 電磁感測器的 ±1 Hz 內；另有 404 位無症狀成人在家完成無人監督的網路攝影機測驗。這兩項研究驗證的是方法本身，不是這個實作。`,
"Li et al., TapTalk (2024) · TAS Test (2022–2025) · PMC10809289": `Li 等，TapTalk（2024）· TAS Test（2022–2025）· PMC10809289`,

/* why this — pillars, states, comparison matrix */
"Open source": `開放原始碼`,
"Every script is on GitHub, including the scoring code.": `所有程式都放在 GitHub 上，包含評分的程式碼。`,
"Runs locally": `在本機執行`,
"Nothing leaves the machine. The hub serves on 127.0.0.1 and results stay on disk.":
  `沒有資料離開這台電腦。控制中心只在 127.0.0.1 提供服務，結果留在磁碟上。`,
"Two domains, one system": `兩個領域，同一套系統`,
"Hand-motor and oculomotor tests in the same session, written to the same results format.":
  `手部動作與眼球運動測驗在同一次流程中完成，並寫入相同的結果格式。`,
"Thresholds shown as provisional": `門檻標示為暫定`,
"Each metric links the paper it came from, and bands not yet fitted to data are labelled as such.":
  `每項指標都連到它出自的論文；尚未以資料校準的區間都會如此標示。`,
"Yes": `有`,
"No": `無`,
"Partial": `部分`,
"Planned": `規劃中`,
"Not yet": `尚未`,
"Capability": `功能項目`,
"This suite": `本套件`,
"Consumer apps": `消費性 App`,
"TAS Test (research)": `TAS Test（研究）`,
"Motor biomarkers (tapping, spiral)": `動作生物標記（敲擊、螺旋）`,
"Oculomotor anti-saccade": `眼動反向掃視`,
"Speech tasks": `語音作業`,
"Camera-only, no wearable needed": `只需相機，不必穿戴裝置`,
"Open-source / inspectable": `開放原始碼／可檢視`,
"Fully local, no data upload": `全在本機，不上傳資料`,
"Longitudinal self-tracking": `長期自我追蹤`,
"Literature-cited metrics shown in-app": `應用內標示指標的文獻出處`,
"Validated on patient cohorts": `已在病患族群驗證`,
"Wearable co-contraction twin": `穿戴式共同收縮對照`,

/* longitudinal analysis */
"Loading sessions…": `載入紀錄中…`,
"No sessions logged yet": `尚無測驗紀錄`,
"Run a screening test from the dashboard. Each session is saved locally, and its metrics will chart here so you can watch the trend over time.":
  `請從主控台執行一項篩檢測驗。每次紀錄都會存在本機，指標會畫在這裡，方便你觀察長期趨勢。`,
"Go to tests": `前往測驗`,
"No sessions for this test yet.": `這項測驗尚無紀錄。`,
"Total sessions": `總紀錄數`,
"Tests tracked": `追蹤中的測驗`,
"Date range": `日期範圍`,
"All tests": `全部測驗`,
"Test type": `測驗類型`,
"{n} sessions": `{n} 次紀錄`,
"1 session · a trend line appears after your next": `1 次紀錄 · 再測一次就會出現趨勢線`,
"{n} session(s) logged for this type, but none were scoreable for this metric yet.":
  `這個類型已有 {n} 次紀錄，但還沒有一次能計算此指標。`,
"{n} session(s) logged, but none were scoreable for this metric yet.":
  `已有 {n} 次紀錄，但還沒有一次能計算此指標。`,
"{metric} across {n} sessions": `{n} 次紀錄的{metric}`,
"no change": `無變化`,
"vs last": `與上次相比`,
"Typical": `一般`,
"Monitor": `觀察`,
"Follow-up": `建議追蹤`,
"Logged": `已記錄`,
"Finger Tapping": `手指敲擊`,
"Spiral Tracing": `螺旋描繪`,
"Eye Movement": `眼球運動`,
"Big & Fast": `大幅快速`,
"Paced": `跟拍節奏`,
"Not run yet": `尚未測試`,
"Run it once to set your baseline": `先測一次，建立你的基準值`,
"first reading": `首次測量`,
"Rhythm variability": `節奏變異度`,
"Velocity variability": `速度變異度`,
"Anti-saccade error rate": `反向掃視錯誤率`,
"Tap frequency": `敲擊頻率`,
"Confidence": `信賴度`,
"Intervals": `有效間隔`,
"CV 95% CI low": `CV 95% 信賴區間下限`,
"CV 95% CI high": `CV 95% 信賴區間上限`,
"Taps (first 10 s)": `敲擊次數（前 10 秒）`,
"Frequency (first 10 s)": `頻率（前 10 秒）`,
"Rhythm variability (first 10 s)": `節奏變異度（前 10 秒）`,
"Shallow closures": `幅度過小的合攏`,
"Amplitude CV": `幅度 CV`,
"Speed decrement": `速度衰減`,
"Beat-sync SD": `節拍同步 SD`,
"Smoothness index": `平滑度指數`,
"Normalized jerk": `標準化急動度`,
"Completion": `完成度`,
"Anti − Pro latency": `反向 − 順向潛伏期`,
"Corrected errors": `已修正錯誤`,
"Valid trials": `有效試次`,

/* ══ strings rendered from dev.js (sensor glove) ═══════════════════════ */

/* toolchain + board commands */
"Run Setup": `執行安裝設定`,
"Install pyserial": `安裝 pyserial`,
"IMU lib: Rev2 (BMI270)": `IMU 函式庫：Rev2（BMI270）`,
"IMU lib: original (LSM9DS1)": `IMU 函式庫：初代（LSM9DS1）`,
"Compile Firmware": `編譯韌體`,
"Upload Firmware": `上傳韌體`,
"Run Glove Tests": `執行手套測試`,
"Re-read Banner": `重讀識別資訊`,
"Start Stream": `開始串流`,
"Stop Stream": `停止串流`,
"Zero &amp; Reset Span": `歸零並重設範圍`,
"Toggle Diagnostics": `切換診斷輸出`,
"Start Recording": `開始錄製`,
"Stop Recording": `停止錄製`,
"Pause": `暫停`,
"Resume": `繼續`,
"Clear": `清除`,
"Auto-scroll": `自動捲動`,

/* connection */
"Port": `連接埠`,
"Refresh": `重新整理`,
"Connect": `連線`,
"Disconnect": `中斷連線`,
"Serial": `序列埠`,
"connected": `已連線`,
"Disconnected": `未連線`,
"No serial ports found": `找不到序列埠`,
"Install pyserial first — use the button above.": `請先安裝 pyserial — 使用上方的按鈕。`,
"Ports refreshed": `連接埠已更新`,

/* scope toolbar */
"View": `檢視`,
"Stacked": `分層`,
"Overlaid": `疊合`,
"Unit": `單位`,
"Force (N)": `力量（N）`,
"Bend (%)": `彎曲（%）`,
"Accel (g)": `加速度（g）`,
"Gyro (°/s)": `陀螺儀（°/s）`,
"Raw ADC": `原始 ADC`,
"Resistance (Ω)": `電阻（Ω）`,
"Conductance (µS)": `電導（µS）`,
"Window": `時間窗`,
"{n} s": `{n} 秒`,
"Y axis": `Y 軸`,
"Fixed": `固定`,
"Auto": `自動`,
"Median of {n} samples. Display only — recordings stay raw.":
  `{n} 筆樣本的中位數。只影響顯示 — 錄製的資料仍是原始值。`,
"Smooth (display only)": `平滑（僅顯示）`,
"Scope shows at most {n} channels — the tiles below cover the rest.":
  `波形最多顯示 {n} 個通道 — 其餘的請看下方卡片。`,

/* toolchain pills */
"Board": `板子`,
"Unknown — needs pyserial": `無法判斷 — 需要 pyserial`,
"Detected": `已偵測到`,
"Not plugged in": `未插上`,
"Interpreter": `直譯器`,
"missing {names}": `缺少 {names}`,
"Installed": `已安裝`,
"Found": `已找到`,
"mbed_nano core": `mbed_nano 核心`,
"Sketch": `草稿碼`,
"Sketch selection unreadable": `無法讀取草稿碼的選擇`,
"Sketch builds without motion": `草稿碼建置時不含動作感測`,
"{imu} selected, not installed": `已選 {imu}，但尚未安裝`,
" and ": `與`,
", which is not the project's <code>.venv</code>": `，而它不是專案的 <code>.venv</code>`,
"<strong>glove.ino selects <code>{imu}</code>, which is not installed.</strong> Compiling will fail on the missing header. Press <em>{btn}</em> below — or, if that is the wrong chip for this board, change the <code>#define GLOVE_IMU_…</code> line at the top of <code>firmware/glove/glove.ino</code> to match the silkscreen.":
  `<strong>glove.ino 選擇了 <code>{imu}</code>，但它尚未安裝。</strong>編譯會因為找不到標頭檔而失敗。
   請按下方的<em>{btn}</em> — 若這顆晶片不是這塊板子上的，請改
   <code>firmware/glove/glove.ino</code> 開頭的 <code>#define GLOVE_IMU_…</code>，
   讓它符合板子絲印上的型號。`,
"<strong>{names} {isare} not importable by this hub.</strong> It is running <code>{py}</code>{venv}. Either restart it with <code>run_hub.bat</code>, or use the install button below — that installs into the interpreter this hub is actually using.":
  `<strong>這個控制中心無法匯入 {names}。</strong>它執行的是 <code>{py}</code>{venv}。
   請改用 <code>run_hub.bat</code> 重新啟動，或按下方的安裝按鈕 —
   那會安裝到控制中心實際使用的直譯器。`,

/* banner */
"No banner yet — connect and the board announces its firmware, rate and column layout.":
  `尚未收到識別資訊 — 連線後板子會回報韌體、取樣率與欄位配置。`,
"Firmware": `韌體`,
"Protocol": `通訊協定`,
" (supported)": `（支援）`,
" (UNSUPPORTED)": `（不支援）`,
"Rate": `取樣率`,
"{bits}-bit @ {mv} mV": `{bits} 位元 @ {mv} mV`,
"Divider": `分壓`,
"Channels": `通道`,

/* channel tiles */
"No channels yet.": `尚無通道。`,
"fsr": `力量感測`,
"flex": `彎曲感測`,
"accel": `加速度`,
"gyro": `陀螺儀`,
"unknown": `未知`,
"peak": `峰值`,
"bar": `長條`,
"open": `開路`,
"no contact": `未接觸`,
"below {n} N actuation": `低於 {n} N 的啟動門檻`,
"datasheet ±{tol}%": `規格書 ±{tol}%`,
"beyond rated {n} N — upper bound only": `超過額定的 {n} N — 僅為上限值`,
"{pct}% bend": `彎曲 {pct}%`,
"no signal": `無訊號`,
"provisional span — bend the sensor to set its range": `暫定範圍 — 請彎折感測器以設定它的範圍`,
"flatter than recorded — re-record span": `比記錄到的更平 — 請重新記錄範圍`,
"bent than recorded — re-record span": `比記錄到的更彎 — 請重新記錄範圍`,
"calibrated span": `已校正範圍`,
"observed span — not calibrated": `觀測到的範圍 — 未校正`,
"unknown sensor — raw only": `未知的感測器 — 只顯示原始值`,
"onboard {imu}": `板載 {imu}`,
"rotation rate": `旋轉速率`,
"proper acceleration": `固有加速度`,
"peak {peak}  ·  adc span {lo}–{hi} of {max}": `峰值 {peak}  ·  ADC 範圍 {lo}–{hi}／共 {max}`,

/* motion card */
"Connect the board to read its onboard accelerometer and gyroscope.":
  `連線板子即可讀取板載的加速度計與陀螺儀。`,
"moving": `移動中`,
"Tilt pitch / roll — board axes": `傾角 俯仰／翻滾 — 板子座標軸`,
"Tilt — hold still, this needs gravity alone": `傾角 — 請保持不動，這需要只剩重力的狀態`,
"Acceleration magnitude — 1.00 g at rest": `加速度大小 — 靜止時為 1.00 g`,
"Motion RMS — movement about its own mean": `動作 RMS — 相對自身平均的變動`,
"Rotation RMS": `旋轉 RMS`,
"Tremor peak in {lo}–{hi} Hz": `{lo}–{hi} Hz 內的震顫峰值`,
"Tremor peak — not enough data yet": `震顫峰值 — 資料還不夠`,
"Share of movement power in the tremor band": `震顫頻帶佔動作能量的比例`,
"{pct}% of frames repeated the previous IMU sample — the chip's own rate is below {fs} Hz, which flattens the top of the band":
  `有 {pct}% 的畫格重複了前一筆 IMU 取樣 — 晶片本身的取樣率低於 {fs} Hz，會壓平頻帶的高端`,
"{s} s window at {fs} Hz · {imu}": `{s} 秒視窗，{fs} Hz · {imu}`,

/* stream health */
"Measured rate": `實測速率`,
"(target {n})": `（目標 {n}）`,
"Dropped frames": `掉格數`,
"Frames received": `已接收畫格`,
"Connected for": `已連線時間`,
"off": `關閉`,
"Recording": `錄製`,
"Rows recorded — {path}": `已錄製列數 — {path}`,

/* scope canvas */
"now": `現在`,
"{n} channels hidden — not {kind}": `已隱藏 {n} 個通道 — 不是{kind}`,
"{n} hidden — not {kind}": `已隱藏 {n} 個 — 不是{kind}`,
"% of observed range": `觀測範圍的百分比`,
"provisional range": `暫定範圍`,
"a force sensor": `力量感測器`,
"a bend sensor": `彎曲感測器`,
"an accelerometer axis": `加速度計軸`,
"a gyroscope axis": `陀螺儀軸`,
"that kind": `這個種類`,
"no channels yet — connect the board": `尚無通道 — 請先連線板子`,
"no {kind} on this board — check the banner's chan= field":
  `這塊板子沒有{kind} — 請檢查識別資訊的 chan= 欄位`,
"no {kind} selected — tick one in the tiles below": `未選取{kind} — 請在下方卡片勾選一個`,


/* ── Remote sessions (docs/REMOTE_SESSION_PLAN.md) ───────────────────── */
"remote.h1": `遠端測驗`,
"remote.intro": `把連結傳給不在現場的人。對方用手機或平板打開，在瀏覽器裡完成測驗，量測結果會回到這台電腦，並與本機測驗一起顯示在<strong>趨勢分析</strong>中。攝影機影像不會離開對方的裝置 &#8212; 只有數值會傳回。規劃文件：<code>docs/REMOTE_SESSION_PLAN.md</code>。`,
"remote.sec.invite": `建立連結`,
"remote.invite.legend": `預設 48 小時後失效，僅限使用一次`,
"remote.sec.links": `已寄出的連結`,
"remote.sec.inbox": `收件匣`,
"remote.inbox.legend": `等待收取的測驗結果`,
"remote.disclaimer": `遠端測驗<strong>無法驗證身分</strong> &#8212; 上面的名字是受測者自行輸入的。現場沒有人協助調整光線或取景，因此當畫面品質低於門檻時，測驗會拒絕評分，而不是給出一個不可信的數字。`,

/* remote.js — English source string is the key */
"The inbox is not connected yet.": `收件匣尚未連線。`,
"Links can be created and the results path can be tested locally, but nothing is pulled from the cloud until these are set:": `目前仍可建立連結，也可以在本機測試結果寫入流程，但在下列項目設定完成前不會從雲端收取資料：`,
"Remote inbox connected.": `遠端收件匣已連線。`,
"Results uploaded by a participant are pulled into results/ and appear in Analysis.": `受測者上傳的結果會收進 results/，並顯示在趨勢分析中。`,
"Test": `測驗`,
"Mode": `模式`,
"Language": `語言`,
"Who is it for?": `受測者`,
"First name": `名字`,
"Expires in (hours)": `有效時數`,
"Times it can be used": `可使用次數`,
"Create link": `建立連結`,
"Copy": `複製`,
"Cancel": `取消連結`,
"Live": `有效`,
"Used": `已使用`,
"Expired": `已過期`,
"Cancelled": `已取消`,
"expires": `到期`,
"{live} live of {total}": `{total} 個連結中有 {live} 個有效`,
"{n} result(s) received": `已收到 {n} 筆結果`,
"No links yet. Create one above and send it however you normally message that person.": `尚未建立連結。請在上方建立，並用你平常聯絡對方的方式傳過去。`,
"Check for new results": `收取新結果`,
"Filed results appear in Analysis.": `收取的結果會出現在趨勢分析中。`,
"Connect the inbox to pull results from the cloud.": `請先連線收件匣，才能從雲端收取結果。`,
"Link copied.": `連結已複製。`,
"Could not copy — select the link and copy it.": `無法複製 — 請手動選取連結後複製。`,
"Add a first name so you can tell the results apart.": `請填寫名字，才能分辨不同的測驗結果。`,
"Finger Tapping": `手指敲擊`,
"Spiral Tracing": `螺旋描繪`,
"Eye Movement": `眼球運動`,
"max": `最快速度`,
"paced": `跟拍節奏`,
"self": `自訂速度`,
"pro_anti": `順向／反向`,


/* ── Session reports (report.js) + the Analysis page's click affordances ──
   The verdict labels come from Python (the metrics modules under core/) and are saved into
   results/ in English, so they are translated here at draw time only — the
   stored record stays one language, and the longitudinal history does not
   split when somebody switches. */

/* the verdicts each test writes */
"Within typical range": `在典型範圍內`,
"Mild variability - consider monitoring": `輕微變異 － 建議持續觀察`,
"Elevated variability - recommend follow-up": `變異偏高 － 建議進一步追蹤`,
"Smooth, well-controlled tracing": `描繪平順、控制良好`,
"Mild jitter - consider monitoring": `輕微抖動 － 建議持續觀察`,
"Marked jitter - recommend follow-up": `抖動明顯 － 建議進一步追蹤`,
"Smoothness unavailable": `無法計算平順度`,
"Mildly elevated - consider monitoring": `略為偏高 － 建議持續觀察`,
"Elevated - recommend follow-up": `偏高 － 建議進一步追蹤`,
"Steady fixation": `注視穩定`,
"Mildly unsteady - consider monitoring": `略不穩定 － 建議持續觀察`,
"Unsteady - recommend follow-up": `不穩定 － 建議進一步追蹤`,

/* Analysis page — the way in */
"Open a report from any chart point, or choose a date in the calendar":
  `點選圖表上的任一點，或從日曆選擇日期，即可開啟完整報告`,
"colour is the verdict the test gave that session": `顏色是該次測驗自己的判讀`,
"Open the report for {when}": `開啟 {when} 的報告`,
"click for the full report": `點選查看完整報告`,
"Session calendar": `測驗日曆`,
"{days} active days · {n} sessions": `{days} 個測驗日 · {n} 場測驗`,
"Previous month with sessions": `上一個有測驗的月份`,
"Next month with sessions": `下一個有測驗的月份`,
"{date}: {n} session(s)": `{date}：{n} 場測驗`,
"View report": `查看報告`,
"{n} session(s)": `{n} 場測驗`,

/* drawer chrome */
"Loading session…": `正在載入這次測驗…`,
"That session could not be loaded. Reports are read from this machine's results folder, so the hub has to be running.":
  `無法載入這次測驗。報告是從這台電腦的 results 資料夾讀出來的，因此 Hub 必須正在執行。`,
"Previous session": `上一場`,
"Next session": `下一場`,
"Close": `關閉`,
"left": `左手`,
"right": `右手`,
"Not scoreable": `無法評分`,
"This recording did not meet the quality gate, so no score was computed.":
  `這段錄製沒有通過品質門檻，因此沒有計算分數。`,
"remote · {who}": `遠端 · {who}`,
"unnamed": `未具名`,
"Every metric": `全部指標`,
"How it was recorded": `錄製條件`,
"Camera": `攝影機`,
"App version": `程式版本`,
"Hand in frame": `手在畫面內`,
"Face in frame": `臉在畫面內`,
"Calibration": `校正`,
"closed": `閉合`,
"centre": `中央`,
"Session id": `場次編號`,
"yes": `是`,
"no": `否`,

/* finger tapping trace */
"The recording": `錄製波形`,
"Thumb-to-finger distance for the whole take. Every tap the detector accepted is marked.":
  `整段錄製中拇指與食指之間的距離。每一次被判定成立的敲擊都有標記。`,
"Finger distance over the recording, with each tap marked": `錄製期間的手指距離，並標出每一次敲擊`,
"tap": `敲擊`,
"calibrated open / closed": `校正出的張開／閉合`,
"tap thresholds": `敲擊判定門檻`,
"metronome beat": `節拍聲`,
"Interval by interval": `逐次間隔`,
"Each interval between taps": `每兩次敲擊之間的間隔`,
"Bar height is the gap between two taps; colour is how far that gap sat from your own mean. An even row is a low CV%.":
  `長條的高度是兩次敲擊之間的間隔，顏色代表這個間隔離你自己的平均值有多遠。整排越整齊，CV% 越低。`,
"mean": `平均`,
"interval {n}": `第 {n} 個間隔`,

/* spiral trace */
"What you drew": `你畫出來的軌跡`,
"Your fingertip path over the template it was aiming at, coloured by how far off the line it was (as a share of the spiral's radius). The ring marks the start.":
  `你的指尖軌跡疊在當時要描的樣板上，顏色代表偏離線的程度（以螺旋半徑的比例計）。圓圈是起點。`,
"The spiral you traced over the template you were following": `你描出的螺旋疊在所依循的樣板上`,
"template": `樣板`,
"on the line": `貼在線上`,
"drifting": `略有偏移`,
"off the line": `偏離線外`,
"Speed through the turn": `描繪過程的速度`,
"How fast the fingertip moved. Even tracing holds one height; velocity variability is this line's scatter.":
  `指尖移動的快慢。描得穩的話這條線會維持在同一高度；速度變異就是這條線的起伏。`,
"Tracing speed over time": `描繪速度隨時間的變化`,

/* oculomotor trials */
"Trial by trial": `逐次測試`,
"Each square is one trial, numbered in order, showing its latency in ms. Open one to see where the eyes actually went.":
  `每個方塊是一次測試，依序編號，上面是那一次的反應時間（毫秒）。點開可以看到眼睛實際往哪裡動。`,
"pro": `順向`,
"anti": `反向`,
"Pro-saccade — look at it": `順向掃視 — 看向亮點`,
"Anti-saccade — look away": `反向掃視 — 看向相反邊`,
"correct": `正確`,
"looked at the target": `看向目標`,
"corrected": `自行修正`,
"too early": `過早反應`,
"no response": `沒有反應`,
"face lost": `失去臉部`,
"Select a trial above.": `請先在上方選一次測試。`,
"That trial has no gaze trace.": `這次測試沒有視線軌跡。`,
"Gaze position through one trial": `單次測試中的視線位置`,
"correct side": `正確方向`,
"target on the left": `目標在左邊`,
"target on the right": `目標在右邊`,
"Holding still": `保持不動`,
"Gaze position while holding still": `保持不動時的視線位置`,
"{n} intrusions": `{n} 次侵入性掃視`,

/* metric names in the report grid (report.js MET) */
"Taps": `敲擊次數`,
"Mean interval": `平均間隔`,
"Interval SD": `間隔標準差`,
"Mean amplitude": `平均振幅`,
"Beat latency": `對拍延遲`,
"Hits": `對上`,
"Misses": `漏拍`,
"Frames": `影格數`,
"Mean speed": `平均速度`,
"Speed SD": `速度標準差`,
"Tremor band power": `顫抖頻段能量`,
"Tremor peak": `顫抖主頻`,
"Mean deviation": `平均偏離`,
"Active time": `有效時間`,
"Anti-saccade latency": `反向掃視反應時間`,
"Pro-saccade latency": `順向掃視反應時間`,
"Latency CV": `反應時間 CV`,
"Anticipatory": `過早反應`,
"Valid anti trials": `有效反向次數`,
"Valid pro trials": `有效順向次數`,
"Face visible": `臉部可見比例`,
"Fixation jitter (RMS)": `注視抖動（RMS）`,
"Fixation BCEA": `注視 BCEA`,
"Saccadic intrusions": `侵入性掃視`,
"Intrusion rate": `侵入性掃視頻率`,
"Fixation analysed": `注視分析時長`,

};

/* ══ server-sent text ══════════════════════════════════════════════════
   Toasts and glove notes are written in Python (launcher.py,
   core/glove/serial_io.py) and arrive in English. Rather than teach the
   server a language, the known strings are matched here; anything unknown
   is shown exactly as sent, never blanked.

   `suffix` is peeled off first — launcher.py appends these fragments to
   messages whose head is matched by `exact` or `rules`. */
window.ZH_MSG = {

exact: {
  "Launched.": `已啟動。`,
  "Stopping.": `正在停止。`,
  "Already running.": `已在執行中。`,
  "Not running.": `未在執行。`,
  "Unknown endpoint": `未知的端點`,
  "Pair this browser with the hub first.": `請先將這個瀏覽器與 Hub 配對。`,
  "Enter a stream URL.": `請輸入串流網址。`,
  "Stream URL must start with http:// or rtsp://.":
    `串流網址必須以 http:// 或 rtsp:// 開頭。`,
  "Done": `完成`,
  "Failed": `失敗`,
  "pyserial is not installed. Use the Install pyserial button.":
    `尚未安裝 pyserial。請使用「安裝 pyserial」按鈕。`,
  "No port selected.": `未選擇連接埠。`,
  "Not connected.": `未連線。`,
  "Already recording.": `已在錄製中。`,
  "Not recording.": `未在錄製。`,
  "Connect to the board first.": `請先連線到板子。`,
  "Running setup…": `正在執行安裝設定…`,
  "Running glove tests…": `正在執行手套測試…`,
  "Compiling firmware…": `正在編譯韌體…`,
  "No port selected — pick the board's port first.": `未選擇連接埠 — 請先選擇板子的連接埠。`,
  "No banner yet — connect the board.": `尚未收到識別資訊 — 請先連線板子。`,
  "This firmware reports no IMU. Install Arduino_LSM9DS1 or Arduino_BMI270_BMM150 to match the board revision, then re-flash.":
    `這版韌體回報沒有 IMU。請依板子版本安裝 Arduino_LSM9DS1 或 Arduino_BMI270_BMM150，然後重新燒錄。`,
  "Banner declares an IMU but the six motion columns are missing from cols=.":
    `識別資訊宣告了 IMU，但 cols= 中缺少那六個動作欄位。`,
  "No motion samples in the buffer yet.": `緩衝區內還沒有動作取樣。`,
  "Give the profile a name.": `請為這位受測者填寫姓名。`,
  "Profile saved.": `受測者已儲存。`,
  "Profile removed.": `受測者已移除。`,
  "That profile no longer exists.": `那位受測者已不存在。`,
  "That is as many profiles as this hub keeps.": `受測者數量已達這個 Hub 的上限。`,
  "Sessions will be saved unassigned.": `之後的紀錄將不指定受測者。`,
  "Session is now unassigned.": `這筆紀錄已改為未指定受測者。`,
  "Session not found.": `找不到這筆紀錄。`,
},

rules: [
  {re: /^Connected to (.+)\.$/,            zh: `已連線至 $1。`},
  {re: /^Already connected to (.+)\.$/,    zh: `已經連線至 $1。`},
  {re: /^Disconnected from (.+)\.$/,       zh: `已中斷與 $1 的連線。`},
  {re: /^Could not open ([^:]+): (.+)$/,   zh: `無法開啟 $1：$2`},
  {re: /^Sent (.+)\.$/,                    zh: `已送出 $1。`},
  {re: /^Unknown command: (.+)$/,          zh: `未知的指令：$1`},
  {re: /^Write failed: (.+)$/,             zh: `寫入失敗：$1`},
  {re: /^Could not start recording: (.+)$/, zh: `無法開始錄製：$1`},
  {re: /^Recording to (.+)$/,              zh: `正在錄製到 $1`},
  {re: /^Saved (\d+) rows to (.+)$/,       zh: `已將 $1 列存到 $2`},
  {re: /^Unknown tool: (.+)$/,             zh: `未知的工具：$1`},
  {re: /^'(.+)' is using the camera\. Stop it first\.$/, zh: `「$1」正在使用相機，請先停止它。`},
  {re: /^Script not found: (.+)$/,         zh: `找不到指令碼：$1`},
  {re: /^Camera set to (.+)\.$/,           zh: `相機已設為 $1。`},
  {re: /^Recording for (.+)\.$/,           zh: `目前受測者為 $1。`},
  {re: /^Session moved to (.+)\.$/,        zh: `紀錄已改指定給 $1。`},
  {re: /^Could not save the profile: (.+)$/, zh: `無法儲存受測者資料：$1`},
  {re: /^Unknown profile action: (.+)$/,    zh: `未知的受測者操作：$1`},
  {re: /^Could not save the camera choice: (.+)$/,
                                           zh: `無法儲存相機設定：$1`},
  {re: /^Failed to launch: (.+)$/,         zh: `啟動失敗：$1`},
  {re: /^Failed to stop: (.+)$/,           zh: `停止失敗：$1`},
  {re: /^Failed to start: (.+)$/,          zh: `啟動失敗：$1`},
  {re: /^Installing pyserial into (.+)…$/, zh: `正在把 pyserial 安裝到 $1…`},
  {re: /^Installing (.+) — re-flash the firmware afterwards\.$/,
   zh: `正在安裝 $1 — 完成後請重新燒錄韌體。`},
  {re: /^Uploading to (.+)…$/,             zh: `正在上傳到 $1…`},
  {re: /^Unknown task: (.+)$/,             zh: `未知的工作：$1`},
  {re: /^Unknown IMU library: (.+)$/,      zh: `未知的 IMU 函式庫：$1`},
  {re: /^Unknown endpoint: (.+)$/,         zh: `未知的端點：$1`},
  {re: /^Needs at least (\d+) s of samples at a rate that resolves (.+) Hz\.$/,
   zh: `至少需要 $1 秒的取樣，且取樣率要能解析 $2 Hz。`},
],

suffix: [
  {re: / — the port is held by something else\. Close the Arduino Serial Monitor or press_test\.ps1 and try again\.$/,
   zh: ` — 連接埠被其他程式占用。請關閉 Arduino 序列監控視窗或 press_test.ps1 後再試一次。`},
  {re: / Disconnected the live stream first — reconnect when it finishes\.$/,
   zh: ` 已先中斷即時串流 — 完成後請重新連線。`},
],

};
