# 每週核准專利 API

更新：2026-09-15。此功能已納入 `weekly`；歐洲已做真實請求，美國等待有效 USPTO key 實測。

## 歐洲：EPO Publication Server

直接使用官方 REST 服務，目前已實測無須金鑰。範圍為歐洲專利局公開的 EP 專利，不是所有歐盟各國國內專利的全集。

1. 取得公開日期清單：`https://data.epo.org/publication-server/rest/v1.2/publication-dates`。
2. 取得日期批次全部案號，例如 `.../publication-dates/20260909/patents`。
3. 完整列舉該批 B 類文件，保存核准／修訂清單與批次原始回應。
4. 逐批取得詳細 XML：`.../patents/EP2151037NWB1/document.xml`。
5. 未完成詳細資料留在佇列；下週先補漏並重新掃描日期重疊區間。

**B1 是核准公開；B2、B3 是修訂／限縮後文件；B8、B9 是更正。** 後者不當作新的獨立核准。2026-09-09 實際批次列舉得到 1,832 件 B1 及 20 件其他 B 類事件。列舉不代表所有全文已取回或已分析。

預設每次最多取得 2 件詳細 XML，設定 `collection.grant_details_per_run` 可調高。第一階段提供 Codex 的是書目、英文摘要／請求項，明示 `grant_bibliography_and_claims`；完整 XML 保留本機，說明書尚不包含在此分析階段。未取得或未閱讀的部分不能算完成。

```powershell
# 只更新完整批次清單，不下載詳細 XML
.\.venv\Scripts\python.exe -m edgefinance collect --sources epo-grants --limit 0

# 依設定下載詳細文件、補抓與理解
.\.venv\Scripts\python.exe -m edgefinance collect --sources epo-grants
.\.venv\Scripts\python.exe -m edgefinance resume
```

[EPO 官方 REST 服務](https://www.epo.org/en/searching-for-patents/data/web-services/publication-server)、[文件分類與每週更新說明](https://www.epo.org/en/searching-for-patents/technical/publication-server/help)。通常每週三公開，程式以官方可見批次為準。

## 美國：ODP API + 核准專利 XML 批次

使用 `USPTO_API_KEY`，由 API 取得 PTGRXML 產品資料，再使用回應提供的 `fileDownloadURI` 下載每週 `ipgYYMMDD.zip`，不自行猜 ZIP 下載網址。

目前產品請求為 `https://api.uspto.gov/api/v1/datasets/products/PTGRXML`。依 ZIP 所代表的核准日期篩選，保留未完成批次；不是用網站目錄修改日期冒充核准日期。美國一般 utility 專利的 B1、B2 都可以是核准公開，不能套用 EPO 的 B2 修訂語意。

```dotenv
# 寫入本機 .env，不放 GitHub，也不貼在對話中
USPTO_API_KEY=YOUR_OWN_KEY
```

```powershell
.\.venv\Scripts\python.exe -m edgefinance collect --sources uspto-grants
.\.venv\Scripts\python.exe -m edgefinance resume
```

預設每次 1 個 ZIP、單檔下載上限 1,024 MiB、每檔匯入最多 500 件；可在 `settings.toml` 調整。中斷留下 `.zip.part`，下次重新下載該未完成 ZIP；已完成 ZIP 不重下載，專利匯入使用記錄游標接續。

本機目前沒有 USPTO key，因此**此 API 路徑仍是待真實帳號驗證的接入實作**：目前已測日期篩選、資料結構解析、去重／續跑與不把 key 送到非官方下載主機；尚未用有效帳號下載正式批次。若官方回應格式、檔案主機或重新導向與目前契約不符，程式會保留失敗，不會顯示成功。屆時可用官網下載 ZIP 的既有入口，不影響其他研究流程。

[ODP Product Data](https://data.uspto.gov/apis/bulk-data/product)、[ODP API key 要求](https://data.uspto.gov/apis/bulk-data/search)、[網頁下載](https://data.uspto.gov/bulkdata/datasets)。

## 對研究的作用

新公開申請用於較早發現研發方向；新核准與後續修訂用於確認權利文件進展。兩條線並行，搭配申請日、優先權、家族、剩餘年限、公司歸屬及商業證據。新核准可能是多年前提交的技術，不能直接解讀為剛發明或即將大賣。

網頁 `patents.html` 提供本週案號、事件種類、來源和詳細資料狀態；每版機器資料 `patents.json` 可供其他程式讀取。`data/patent-feeds/` 保留跨週清單、批次與待處理項目。核准公開的確認不等於已確認目前權利有效或權利人未變更。

## 台灣：公報列舉 + 個案 API 補全

`tipo-grants` 每週先呼叫智慧局公開的網路公報介面，取得公報期別，再枚舉該期發明、新型與設計的全部核准書目。每筆保留證書號、申請號、標題、申請人、發明人、公報 PDF、卷期及公告日；主題或公司候選案才進入 Codex 詳讀佇列。

使用者核發的 `TIPO_API_USERNAME` 與 `TIPO_API_PASSWORD` 只傳送到 `tiponet.tipo.gov.tw` 的固定 HTTPS 端點。系統先取得短期 Bearer token，再依已知申請號取得案件書目、優先權、關聯案與程序文件歷程。token 回應不保存、不寫 log，也不進公開 JSON。手冊這組 API 沒有「列出最新案件」功能，因此不能單靠帳密做每週全量發現；最新案件由公開公報介面負責。

台灣公報通常每月有多個期別。程式每週執行時會用重疊窗口偵測新期別，完整保留書目索引，並依 `tipo_details_per_run` 分批補全候選案。公報核准不等於專利目前仍有效，公司歸屬也只有精確名稱候選；投資論點仍需搭配家族、引證、法律狀態、公司財務與商業化證據。
