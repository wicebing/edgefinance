# EdgeFinance Podcast 與 YouTube 本機流程

## 產製順序

```powershell
.\scripts\weekly.cmd
.\scripts\podcast.cmd
.\scripts\youtube.cmd
```

`weekly.cmd` 先凍結可追溯週報。`podcast.cmd` 再從最新凍結版本建立最多 24 項的媒體資料包，優先保留論點、反證與 14／30／90／180 天風險卡實際引用的證據。Codex 只能使用資料包中的證據 ID，無法通過驗證的稿件不會送進 TTS。

## Ying 與 Bing

- Ying：`../tts/girl voice.m4a`，證據與產業研究主持人。
- Bing：`../tts/man voice.m4a`，投資風險與反方論證主持人。
- 引擎：本機 XTTS v2，講稿、口語與所有 YouTube 文案均使用美式英文，語音前端為 `en`。
- 聲音 profile：mono、24 kHz，保存在 `data/podcast-voices/`。
- 快取：每個回合以台詞和聲音樣本 SHA-256 建立檔名；同一稿件重跑只混音，不重錄。

這個流程使用使用者已放在本機的聲音樣本。公開 MP3 與影片保留合成語音揭露；上傳前仍應人工試聽並確認聲音權利與內容。

## Podcast 驗證

對話稿必須同時符合：

- 34–56 回合、12–18 分鐘目標，Ying／Bing 回合數差不超過 3。
- 至少 80% 相鄰回合換人，雙方各自提出至少兩個問題。
- 至少 8 個短回應，避免把週報切成兩段輪流朗讀。
- 每個可驗證陳述只能引用資料包內的 `source_ids`。
- 專利不等於產品、營收或股價；篩選分數不等於預期報酬。
- YouTube 說明包含書面週報與本集實際引用的所有來源網址。

公開索引位於 `public-media/podcasts.json`，內容包括音訊、逐字稿時間、章節、fact check、來源和揭露。網站建置會驗證 MP3 存在、檔案大小與時間軸，再複製到 `dist/media/`。

## YouTube 上傳包

```powershell
.\scripts\youtube.cmd
```

輸出在 `youtube-output/`：

- `edgeFinance4Podcast-YYYY-wNN.mp4`：1280×720、5 fps、H.264、AAC，含 `eng` 字幕軌。
- `edgeFinance4Podcast-YYYY-wNN.srt`：可另外上傳的美式英文字幕。
- `edgeFinance4Podcast-YYYY-wNN-thumbnail.png`：YABILAB 品牌縮圖。
- `*-title.txt`、`*-description.txt`、`*-upload.txt`：標題、說明、標籤、置頂留言與揭露。
- `*-manifest.json`：檔案名稱、bytes 與 SHA-256。

影片以對話回合為畫面單位，顯示主持人、章節與完整當句文字。畫面持續時間使用 TTS 實際時間軸，影片總長以母帶秒數鎖定，避免字幕結束時截掉片尾。

## 常用選項與排錯

```powershell
# 只產生／檢查 Codex 講稿
.\scripts\podcast.cmd --script-only

# 強制重新寫最新一期講稿
.\scripts\podcast.cmd --force-script

# 沒有 CUDA 時
.\scripts\podcast.cmd --device cpu

# 只輸出 YouTube 文案，不渲染影片
.\scripts\youtube.cmd --plan-only
```

若 Anaconda Python 不在預設位置，可設定：

```powershell
$env:EDGEFINANCE_PODCAST_PYTHON = "C:\Path\To\python.exe"
```

若要使用其他 ffmpeg：

```powershell
$env:EDGEFINANCE_FFMPEG = "C:\Path\To\ffmpeg.exe"
```

每週發布前請至少確認：MP3 可完整播放、Ying／Bing 沒有念錯關鍵公司或數字、MP4 長度等於音訊、縮圖可讀、說明中的週報與來源連結可開啟。`youtube-output/` 不進 Git；上傳後可以刪除，不影響網站 Podcast。
