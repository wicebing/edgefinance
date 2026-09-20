# EdgeFinance

每週在本機累積公開資料，使用 **Codex CLI 的 ChatGPT 訂閱登入**逐段閱讀、核對引用，生成繁體中文研究週報及 GitHub Pages 靜態網站。

目前為可運行 v0.3：採集、可恢復儲存、Codex 分段抽取／綜合分析、90／180 天風險卡、全球經濟與台灣即時頁，以及台灣上市櫃、SEC 美國／在美上市國際公司、Bitcoin／Binance 公開現貨與每週專利權利人的研究候選雷達。候選分數只決定查證順序；結論仍是待覆核研究假說，尚無完整估值、總報酬回測或經驗證的選股勝率。

## 開始使用

需求：Python 3.11 以上、已安裝且登入 ChatGPT 的 Codex CLI。

```powershell
.\scripts\setup.ps1
codex login
.\.venv\Scripts\python.exe -m edgefinance doctor
.\.venv\Scripts\python.exe -m edgefinance weekly
.\.venv\Scripts\python.exe -m edgefinance serve
```

開啟 **http://127.0.0.1:8765**，或直接開啟 `dist/index.html`。相對連結支援 GitHub repository Pages 子路徑。

若不使用 PowerShell 腳本，可直接安裝：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
```

每週執行 `weekly`。預設最多 60 個新分析任務；額度或預算不足、來源失敗時保留進度並揭露缺口。接續待讀資料：

```powershell
.\.venv\Scripts\python.exe -m edgefinance resume --max-jobs 60
.\.venv\Scripts\python.exe -m edgefinance status
.\.venv\Scripts\python.exe -m edgefinance validate
```

`resume` 不重新下載；只讀待處理分段，重用通過核對的抽取結果，建立新的報告版本。分段未完成就計入 coverage，不把部分讀完標示成全部讀完。

## 美國專利：先網頁下載，再本機處理

1. 開啟 [USPTO ODP](https://data.uspto.gov/home)，依官網要求登入 USPTO.gov 帳號。
2. 在 [Bulk datasets](https://data.uspto.gov/bulkdata/datasets) 找 **Patent Application Full Text Data/XML**、**Patent Grant Full Text Data/XML**。先選文字 XML ZIP，不需 TIFF 圖片包或全部 File Wrapper。
3. 將完整 ZIP 放進 `data/inbox/uspto/`；不用解壓，每週指令會自動匯入。
4. 可加同名 sidecar，例如 `ipa-example.zip.json`，以 `{"source_url":"官網實際資料集頁面網址"}` 保留精確來源。

也可指定已下載的檔案：

```powershell
.\.venv\Scripts\python.exe -m edgefinance import-uspto "C:\Downloads\patents.zip" --max-records 500
.\.venv\Scripts\python.exe -m edgefinance resume
```

支援 Red Book `us-patent-application`／`us-patent-grant`、多件 XML 串接、ZIP 串流、內容雜湊、游標與重跑去重。預設每檔每次最多 500 件，下次續跑。`--topic-only` 明確篩選研究主題並記錄略過數；預設匯入所有讀到的記錄。公司精確名稱匹配仍只是歸屬候選。尚不含 OCR、化學式重建或歷史 SGML；ZIP 的 XML 解壓總量上限 8 GiB、單件上限 20 MiB，超出會保留未完成狀態。

免費帳號與 API key 是不同層次。ODP 自 2026-06-18 要求登入，API 另有 key 與帳號驗證流程，不承諾所有人的申請一定成功。已下載檔案的本機處理不需要 key；此路徑不繞過官網登入。[帳號說明](https://www.uspto.gov/about-us/usptogov-account)、[登入公告](https://www.uspto.gov/subscription-center/2026/uspto-open-data-portal-require-registration-access-beginning-june-18-2026)、[API 說明](https://data.uspto.gov/apis/bulk-data/search)。

## 現有資料來源

**新增：每週核准專利 API。** EPO B1 核准與 B 類變更完整列舉、分批抓取詳細 XML；美國 ODP 核准 XML 批次下載接入待有效 key 實測。操作、限制及分類差異見 [每週核准專利](docs/WEEKLY_PATENTS.zh-TW.md)。

| 來源 | 已實作方式與限制 |
|---|---|
| SEC | CIK／ticker 核對、Company Facts；30 家起始名單預設前 6 家，選定科目與期間，非全部申報全文 |
| SEC 全市場雷達 | 官方上市代號母體，聯結最近已結束季度與去年同季的 Revenue、Net Income、R&D XBRL Frames；目前可比 2,336 家，會漏掉概念或財年無法對齊者 |
| Federal Reserve、NASA | 官方 RSS 及可取得的文章；全文失敗明示 RSS 摘要，保留重試佇列 |
| EPO | Publication Server 最新公開批次前 3 件；可能只有書目，非主題代表樣本或完整覆蓋 |
| EPO grants | 完整列舉所選週間的核准／修訂案號；預設每次 2 件詳細 XML，佇列接續 |
| US 觀察樣本 | 設定內 3 個 Google Patents 頁面；歷史樣本，非當週全部新申請 |
| USPTO 本機 ZIP/XML | 匯入實際提供的檔案；游標與已處理範圍可查 |
| BLS | 免 key 單一數列 API，失業率／CPI；保留修訂快照，觀察月份不當作公告日期 |
| Treasury | 官方殖利率 XML；本次環境逾時會顯示失敗，不補造數值 |
| FRED／ALFRED | 指定 vintage 的 API，需要 FRED_API_KEY；未以實際 key 驗證 |
| USPTO ODP API | 需要 USPTO_API_KEY，目前只保存產品目錄；全文由下載檔 inbox 接入 |
| USPTO grants API | 另一路核准 XML 產品清單與 ZIP 下載、匯入；尚缺有效 key 驗證 |
| World Bank | 18 個主要經濟體、8 組成長／通膨／就業／外貿／製造／FDI 指標，每組最近 5 個非空值；免 key，為現行修訂版 |
| ECB | 14 種主要貨幣對歐元的官方參考匯率，最近 120 天；免 key，非可成交報價 |
| ECB／BOJ 官方公告 | 官方 feed 發現後取得公告或 PDF；與既有 Federal Reserve feed 一起提供主要央行政策事件 |
| TWSE／TPEx 日行情 | 上市與上櫃普通股最近交易日全市場快照，觀察公司依官方股票代號對應 |
| MOPS 月營收 | 上市櫃全市場營收廣度及觀察公司財務列；單次上限可接續處理，不把未處理標成完整 |
| MOPS 重大訊息 | 上市櫃官方最新重大訊息；作為事件線索，仍需核對附件與後續結果 |
| 台灣全市場雷達 | TWSE／TPEx 行情、MOPS 月營收、PE／PB／殖利率；TPEx 另顯示三大法人淨額但不納入跨市場分數。本期 1,946 家營收可比公司 |
| Binance 公開市場 | `data-api.binance.vision` 的 Exchange Info、24h Ticker 與日 K；排除主要穩定幣後分析高流動性 USDT 現貨樣本，不使用帳戶或交易 API |

調整 `config/settings.toml`、`sources.json`、`topics.json`、`companies.json`。較大範圍增加磁碟、時間及訂閱用量。大量證據會先分層壓縮、保留入選證據 ID，再進行最終綜合；目前不能宣稱讀盡全球資訊。

## 儲存與 MongoDB

| 位置 | 用途 | 放 GitHub？ |
|---|---|---|
| `data/raw/` | gzip 原始回應、SHA-256 定址 | 否 |
| `data/normalized/`、`data/research.sqlite3` | 文件版本、查詢索引 | 否 |
| `data/analysis/`、`data/reports/`、`data/imports/` | 抽取、週報、下載進度 | 否 |
| `data/queues/` | 待取回 RSS 全文 | 否 |
| `work/packs/` | Codex 提示詞、schema、輸出、執行 log | 否 |
| `public-data/v1/` | 分析、來源連結、版本 manifest | 是 |
| `dist/` | HTML／CSS／JS／公開 JSON | 由 Actions 部署 |

原文留本機，精簡分析 JSON 上 GitHub。備份整個 `data/`；`rebuild-index` 可從保存檔補建索引，不清空資料。網站先在新資料夾驗證，成功才替換 `dist`；前版留在 `data/site-backups/`。原始 ZIP 與備份會累積，需依自己的磁碟容量整理。

MongoDB 為選配結果同步。程式讀取現有 `atlas-credentials.env`，不把其值交給模型、網站或 Actions。

```powershell
.\.venv\Scripts\python.exe -m edgefinance doctor --mongodb
.\.venv\Scripts\python.exe -m edgefinance sync-mongodb
```

前者只 ping，後者明確同步到獨立 `edgefinance` 資料庫，每次最多 500 份精簡文件；不改寫舊新聞庫、不自動升級 Atlas。已連線不代表已驗證方案容量。

## Codex、引用與前瞻驗證

Codex 接收隔離的公開資料包，唯讀 sandbox、關閉 shell／外部工具／代理委派。記錄 CLI 版本、提示詞 hash、結果及可取得的 usage；未回傳的模型名稱保持未知。只接受 ChatGPT 訂閱登入，失敗不改用付費 API。

引用必須是來源中的連續原文，論點只能用存在的證據 ID，公司要有對應來源支持。文字比對不代表已確認翻譯、因果、專利所有權或產品營收；首頁保留原文覆核、替代解釋、否證條件與估值缺口。

歷史回補不等於當時已可交易的訊號。分開保留公開、首次取得、產生及可用時間。`--as-of` 篩選來源日期，不把今天取得的修訂值當作過去已知值；前瞻比較要使用當週實際生成的凍結週報。

90／180 天風險卡有期限、傳導、觸發與緩和條件，沒有未校準數字機率。到期後可用 `record-outcome --check-id ... --outcome observed|not_observed|inconclusive --source-url ... --note ...` 記錄條件檢查；這不是投資報酬。

## GitHub Pages

Repository 為 `wicebing/edgefinance`，Pages 預定網址是 **https://wicebing.github.io/edgefinance/**。憑證、本機資料、模型 log 和舊 `News Scrapping/` 已忽略。

Settings → Pages → Source 選 **GitHub Actions**。推送 `main` 或手動執行 `.github/workflows/pages.yml`，Actions 跑離線測試、驗證歷史 manifest、生成並部署 `dist`，不在雲端跑 Codex，也不需要 API 或 MongoDB 憑證。工作流程只部署既有 Pages 站點，不再嘗試用 `GITHUB_TOKEN` 建立站點。每週本機完成、閱讀週報後，再提交新的 `public-data/`。[詳細發布步驟](docs/PUBLISH.zh-TW.md)。

## 台灣智慧局專利

MVP 已接入 `tipo-grants`。每週先完整列出智慧局最新公報中的發明、新型與設計核准書目，再以主題和精確公司名稱篩選候選案；本機 `.env` 的個案 API 帳密只用來補全已知申請號，不會出現在 Git、原始證據或網頁中。

```powershell
.\.venv\Scripts\python.exe -m edgefinance collect --sources tipo-grants
.\.venv\Scripts\python.exe -m edgefinance resume
```

這組個案 API 帳密與「專利商標開放資料 API 驗證碼」是不同權限。現有流程不需要額外驗證碼即可列舉網路公報；大量 XML／圖片仍使用官方 FTPS，首版避免每期下載數 GB 影像。完整資料契約與限制見 [台灣智慧局接入說明](docs/TIPO_PATENTS.zh-TW.md)。

## 測試與下一步

[本次 MVP 實際驗證紀錄](docs/MVP_VALIDATION.zh-TW.md) 列出完成項目與尚未驗證的部分。

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m edgefinance validate
.\.venv\Scripts\python.exe -m edgefinance build-site --from-public
```

新版方向見 [專案規劃 v2](docs/PROJECT_PLAN_V2.zh-TW.md)、[多市場候選雷達](docs/MARKET_RADARS.zh-TW.md) 與 [全球及台灣資料契約](docs/GLOBAL_AND_TAIWAN_SOURCES.zh-TW.md)。其他待辦見 [持續演化清單](docs/EVOLUTION.zh-TW.md)。原始規劃保留：[專案規劃](docs/PROJECT_PLAN.zh-TW.md)、[來源](docs/DATA_SOURCES.zh-TW.md)、[網頁規格](docs/REPORT_AND_SITE_SPEC.zh-TW.md)、[儲存決策](docs/STORAGE_AND_PUBLISHING.zh-TW.md)。規劃不是功能完成清單，實際狀態以本 README 為準。
