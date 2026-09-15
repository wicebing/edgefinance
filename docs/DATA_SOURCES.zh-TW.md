# 公開資料來源與接入清單

> 本文件保留初始規劃及當時檢視紀錄。MVP 已實作，實際功能、驗證與限制以 [README](../README.md) 為準。
查核日期：2026-09-14。這是接入規劃，**尚未完成 API 金鑰申請、資料下載或端到端接入測試**。「文件已查核」只表示已閱讀相應官方頁面；不是 API 可用性、全文完整度或帳號權限保證。

來源先後順序以能否回答研究問題決定。初始原則是官方批次／API → 官方 RSS／公告 → 合法網頁擷取；能取得原始文件時，新聞用來發現線索，再回到原始文件驗證。

## 1. 已查核的核心來源

| ID／優先級 | 來源與官方文件 | 可用內容與接入方式 | 權限、限制與研究注意事項 |
|---|---|---|---|
| PAT-US／P0 | [USPTO ODP bulk search](https://data.uspto.gov/apis/bulk-data/search) | 批次資料產品目錄 API；依產品下載公開申請、授權等所需資料 | API 要金鑰；頁面公告 2026 年起新增登入／帳號資訊要求。先枚舉產品與 schema，再確認目標年份、全文、權利項、修訂和更新頻率。目錄 API 不是單篇專利全文查詢 API |
| PAT-EP-PUB／P0 | [EPO European Publication Server](https://www.epo.org/en/searching-for-patents/data/web-services/publication-server) | 每週公開清單與 EP A／B 文件；REST 可取 XML、HTML、TIFF、PDF/A | 官方目前列每 IP 滾動七日 5 GB；依回應與最新規則調節。首版先抓清單與相關 XML，不大量抓圖片 |
| PAT-EP-OPS／P0 | [EPO OPS](https://www.epo.org/en/searching-for-patents/data/web-services/ops) | 書目、家族、法律事件及可得全文的補充查詢 | 註冊、應用憑證與 OAuth；非付費每週最多 4 GB。家族、搜尋、下載另有流量限制，不適合用免費服務鏡像整庫 |
| PAT-TW／P0 | [智慧局網路公報](https://cloud.tipo.gov.tw/S220/gazette/patent)、個案公開資訊 API | 公報期別與核准案書目可公開枚舉；已核發帳密依申請號補充分類、優先權、關聯案及程序歷程 | 個案 API 不能列舉最新案件；帳密只在本機使用。公報 PDF 與完整說明書採連結，不放入 GitHub。公報更新日、公告日與每週執行日分開記錄 |
| FIN-SEC／P0 | [SEC EDGAR data APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | Submissions、Company Facts 及官方申報文件；JSON 與批次 ZIP | data.sec.gov 讀取 API 不需金鑰；遵守 fair access。公司財務 API 不是股票報價，也不保證包含所有客製 XBRL／產品分部欄位 |
| MACRO-FRED／P0 | [FRED API](https://fred.stlouisfed.org/docs/api/fred/fred/) | 總體、利率、信用等時間序列；按系列與發布更新取得 | 使用註冊金鑰；每條數列保留原始提供者、單位、頻率、季調、修訂與再散布條件 |
| MACRO-ALFRED／P0 | [ALFRED 與 real-time period](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html) | 以時間版本取得當時已知的經濟資料 | 不是所有歷史資料都具有相同版本覆蓋；核對可得期間。不能用今日修訂值冒充過去訊號 |
| NEWS-GDELT／P1 | [GDELT DOC API](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/) | 跨語言新聞探索、文章 URL、媒體關注變化 | 查核的是官方功能文件，部分文件較舊；實作先測搜尋窗口、結果上限與截斷。索引命中不代表全文取得或可再散布 |
| SCI-OPENALEX／P1 | [OpenAlex API](https://help.openalex.org/api/)、[Access](https://help.openalex.org/access/) | 研究作品、作者、機構、引用與相關查詢 | 已確認官方 API 與 access／pricing 文件入口；當前特定端點、認證與免費額度仍需實作前細核。摘要、作者公司關係及全文可能缺失 |
| SCI-ARXIV／P1 | [arXiv API 使用條件](https://info.arxiv.org/help/api/tou.html) | 論文 metadata、摘要、版本與可得內容 | legacy API／RSS／OAI-PMH 為單連線、至少間隔三秒；metadata 與論文全文授權分開。預印本不是已通過同儕審查的保證 |
| TRADE-UN／P1 | [UN Comtrade](https://comtradeplus.un.org/TradeFlow?CommodityCodes=ALL) | 按國家、夥伴、HS 等商品、貿易流向、月／年期間取得統計 | 官方頁面目前列免費註冊金鑰每日 500 次、每次最多 100K records；接入時覆核方案。各國上架時間不固定，數據非公司層級 |
| SHIP-IMF／P1 | [PortWatch catalog API](https://portwatch.imf.org/api/search/definition/)、[2026 年方法研究](https://www.imf.org/en/publications/wp/issues/2026/05/19/nowcasting-country-level-trade-estimates-using-imf-portwatch-576176) | 港口、航道及海運活動衍生資料；先查 catalog 再找對應 dataset service／download | catalog 是資料目錄，不等於數據查詢 endpoint。接入時確認 dataset ID、欄位、時間更新、分頁、方法版本與授權。AIS 衍生估計不是公司艙單 |

P0／P1 表示實作順序，不表示來源品質高低。公司 IR、政府 RSS 與新聞網站仍需逐站登錄，不能以一個「RSS 已接入」代表所有站點已可靠覆蓋。

## 2. 重要限制與設計決策

### 美國與歐洲專利

USPTO ODP 官方目前提供的批次產品搜尋端點為 `GET https://api.uspto.gov/api/v1/datasets/products/search`，需 API key。對照其產品目錄取得實際檔案，而不是沿用舊教學對匿名下載的假設。[ODP 文件](https://data.uspto.gov/apis/bulk-data/search)。

EPO OPS 與 Publication Server 是不同服務，額度、功能、時間窗口不能混用。OPS 官方建議整庫需求使用批次產品，不用一般查詢服務大量搬運資料；使用者需遵守其公平使用與資料再散布條件。[OPS 限制](https://www.epo.org/en/service-support/faq/searching-patents/open-patent-services/general-information/are-there-any)、[OPS 使用條件](https://www.epo.org/en/service-support/ordering/terms-and-conditions/ops-terms-and-conditions)。

EPO 全文批次資料有歷史與每週增量，規模可能達 TB。部分 Euro-PCT 文件不會完整重刊，只有對應資訊，需記錄對應 WO 文件與缺失狀態；不能把 EP 清單上的每一筆都宣稱已取得完整內容。[EP full-text data](https://www.epo.org/en/searching-for-patents/data/bulk-data-sets/data)。

可評估以 EPO Linked Open EP Data 補充結構化關係，其 CC BY 4.0 與使用限制不同於 OPS，必須分開記錄來源授權。[Linked Open EP Data](https://www.epo.org/en/searching-for-patents/data/linked-open-data)。

美國及歐洲的申請公開有時間延遲。從來源取得的 `application_date` 不是系統可用來交易的資訊時間；網站用語應為「本週新公開／新取得專利」。[USPTO](https://www.uspto.gov/web/offices/pac/mpep/s1120.html)、[EPO](https://register.epo.org/help?lng=en&topic=publicationdate)。

每種專利端點的首次驗收：取一個已知家族、包含申請與授權的多文件，核對 applicant、publication、kind code、priority、claims、family、法律狀態與可得範圍；再以一個完整時間窗口核對分頁和下載清單。

### SEC 與公司財務

起始介面採 `submissions/CIK##########.json` 與 `api/xbrl/companyfacts/CIK##########.json`，CIK 補成十位。Submissions 包含近期歷史及更早資料檔案索引，不能只讀第一份 JSON 就當完整歷史。完整報表和分部資訊回到原申報文件。[SEC data APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)。

目前官方公平使用上限為每使用者合計不超過每秒十次請求；設計預設低於上限並識別工具、快取及退避，不能增加機器數來規避。[SEC developer resources](https://www.sec.gov/about/developer-resources)。

財務解析的專案要求：年度／季度／累計期間分開；單位、幣別、期間長度、GAAP／IFRS、重編、公司自定義欄位保留；不得把不同期間同名欄位混加。來源是公司正式申報，也不代表管理層的未來預測已成事實。

### 新聞與研究

GDELT 作為線索和來源 URL 探索。依時間、語言、主題拆查，記錄查詢是否觸及結果上限；若到達上限且不能再拆，標記截斷，不回報完整覆蓋。歷史搜尋能力需實測，因官方不同年份功能文章對時間窗口有變更。[GDELT 搜尋窗口更新](https://blog.gdeltproject.org/doc-geo-2-0-api-updates-full-year-searching-and-more/)。

取得全文遵守原站條件；不能把付費牆錯誤頁當正文。相同通訊社稿、公司新聞稿被十個站轉載，仍屬同一來源家族。每則新聞保留「媒體報導／公司宣稱／官方確認／傳聞」性質。

科學研究記錄版本、撤回、更正與有無獨立重現。對未提供摘要的 metadata，Codex 只能依實際取得內容分類；不能依標題自行生成不存在的摘要。

### 貿易與海運

Comtrade 輸入至少固定 reporter、partner、商品分類版本、flow、period、quantity unit、net weight、value 與貨幣。HS 分類變更、再出口、轉口、雙邊鏡像差異及進出口估值口徑都應註記。

PortWatch 研究可協助理解以海運觀測估計當期貿易的方法，並不等同三個月後股價預測模型。2026 年官方研究也使用額外資料將港口活動轉為國家貿易估計；公司收入需要更進一步的證據。[IMF 國家級研究](https://www.imf.org/en/publications/wp/issues/2026/05/19/nowcasting-country-level-trade-estimates-using-imf-portwatch-576176)。

個別公司艙單與提單資料的可得性、批量權利、隱名與代理商對應另行驗證。美國 CBP 允許申請名稱等資訊的保密處理，因此不可承諾免費、完整追蹤所有公司的進出口。[CBP 說明](https://www.help.cbp.gov/s/article/Article-1108)。

### 股價、估值與績效：不可缺少的一環

本次未選定或驗證全球股價供應商。這是正式投資排序及績效回測的明確待辦，不能用 SEC 或宏觀資料取代。

接入要驗收：交易所與幣別、時區、交易日曆、普通股／ADR、拆分、股息、增資、併購、退市、股票代號變更、歷史有效日與再散布權。現價來源不足時，公司頁仍能呈現技術與財務研究，但估值判斷標「未完成」。沒有完整退市及公司行動資料時，不發表全市場嚴格回測績效。

## 3. 後續擴充候選

以下為接入研究方向，**本次未逐一驗證目前 API、金鑰、額度或授權，不能當成已可用來源**。

| 類型 | 待評估來源 | 想補足的證據 | 先驗收什麼 |
|---|---|---|---|
| 台灣公司 | 公開資訊觀測站、TWSE、TPEx、政府開放資料 | 月營收、財報、重大訊息、股價與公司行動 | 可自動取得介面、原始發布時間、修訂和再散布 |
| 歐洲當地上市公司 | 各國官方申報系統、公司 ESEF／IR、ESMA 相關資料入口 | 非 SEC 申報公司的財務與公司資訊 | 跨國覆蓋、ESEF 解析、語言、時點及有效識別碼 |
| 其他專利 | WIPO／PATENTSCOPE、各國專利局、PatentsView、授權專利資料商 | WO／PCT、國內專利與整理後的申請人 | 大量取得權利、歷史版本、最新更新與斷層 |
| 經濟與金融 | ECB、BIS、OECD、World Bank、IMF、各國統計局 | 利率、信用、匯率、全球成長與財政 | 數列定義、頻率、修訂、API 變更及授權 |
| 能源與航運 | EIA、各港務局、UNCTAD、WTO、官方運河統計 | 能源供需、港口吞吐、航線瓶頸與貿易 | 空重櫃、TEU／噸／貨值、地區與船型可比性 |
| 科研投入 | Crossref、CORDIS、NSF、NIH、各國研發補助 | 技術資金、機構合作、論文和資助關係 | 補助日期、實際撥款、機構與公司映射 |
| 商業化 | 政府採購、產品核准、標準組織、公司產品文件 | 採購、認證、標準採用與產品規格 | 宣告／核准／交付／收入辨識及全文權利 |
| 供應鏈投入 | 公司資本支出、廠房許可、環評、法說、公開招募 | 擴產與能力建置 | 正式計畫與實際進度分開，非標準來源品質 |
| 國際事件 | 官方公報、央行公告、貿易／制裁主管機關、天然災害與氣象機構 | 政策原文、生效日與可觀測衝擊 | 官方來源核對、修訂、地理位置與暴露 |
| 市場驗證 | 合法行情與基本面資料供應商／交易所 | 股價、估值、總報酬、流動性、退市資料 | 所選市場與歷史覆蓋、公司行動完整性、使用權 |

專業指數、法說逐字稿、海關資料、標準全文與專利整理資料不預設免費。先以官方可得資訊形成閉環，再以對研究增益的實測決定是否加購。

## 4. 每個來源的登錄契約

實作為設定檔與資料庫，至少包含：

```text
source_id / display_name / owner / official_docs_url
verification_status: candidate | docs_checked | sample_verified | operational
docs_checked_at / sample_verified_at / schema_version / terms_checked_at
access_method: api | bulk | rss | permitted_web
credential_env_names                 # 僅保存環境變數名稱
scope / languages / date_range / expected_cadence / release_lag
cursor_strategy / overlap_window / pagination / max_results
rate_limit / byte_budget / retry_policy / timeout
rights_status / attribution / redistribution_policy / retention_policy
raw_format / parser_version / record_id_fields / hash_strategy
quality_checks / monitoring / fallback / owner_notes
```

`candidate` 沒有資格自動啟用；`docs_checked` 還需真實樣本；`sample_verified` 需完成歷史／增量／故障測試才升為 `operational`。欄位缺失、返回空清單、來源暫停與真正沒有新資料應有不同狀態。

## 5. 覆蓋率與接入驗收

按來源、地區、語言、期間、文件類型顯示：預期筆數（來源提供時）、實際取得、去重後數量、全文率、解析成功、公司匹配、初讀／深讀、更新延遲、引用與失敗。

沒有母體數量時標「覆蓋率未知」，只回報觀測數與查詢範圍；不能以已抓筆數除以搜尋結果上限作全球覆蓋率。

每個接入模組需通過：跨頁取樣、重跑去重、斷線續傳、錯誤及限流回應、延遲發布與更正、同一 ID 多版本、空資料、解析失敗、來源時間與時區、原始檔雜湊、授權公開欄位、真實樣本人工核對。付費來源額外確認成本上限，不可隱性開啟。

## 6. 執行與發布依賴

- [Codex 非互動模式](https://learn.chatgpt.com/docs/non-interactive-mode)：本機批次理解；輸出 schema、事件與最終結果分開保存。
- [Codex 登入](https://learn.chatgpt.com/docs/auth)、[額度](https://learn.chatgpt.com/docs/pricing)：預設訂閱登入，實際限制隨方案與使用狀態；不設定固定免費處理量。
- [GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages)、[使用限制](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)：靜態公開產物；目前站點上限 1 GB、每月流量軟上限 100 GB。完整原始資料庫放本機與備份儲存，避免長期膨脹的 Git 儲存庫。

回到 [完整專案規劃](PROJECT_PLAN.zh-TW.md) 或 [網站與週報規格](REPORT_AND_SITE_SPEC.zh-TW.md)。
