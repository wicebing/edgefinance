# 首頁、週報與證據格式

> 本文件保留初始規劃及當時檢視紀錄。MVP 已實作，實際功能、驗證與限制以 [README](../README.md) 為準。
版本：v0.1｜日期：2026-09-14｜狀態：產品與資料契約設計，畫面與範例均不是實際投資結論。

## 1. 首頁應讓人先看到什麼

首頁是累積至本週的研究判斷。週報是歷史快照。兩者引用同一個版本化證據庫，首頁不能只貼最新新聞摘要，也不能讓新一週自動清空上一週的長期機會。

```text
EdgeFinance       機會地圖  技術  公司  風險  歷史週報  方法與資料

資料截至 [時間／時區]    最新週報 [週別]    本期狀態 [完整／部分]
本週改變了什麼：新增論點／證據增強／降級／失效／待查證

長期機會                                  90 天／180 天風險
[技術與公司候選卡]                         [兩個期限的風險矩陣]
判斷、價值取得、成熟區間、證據             事件、暴露、觸發與緩和條件
本週變化、估值狀態、主要反證               相對上週的變化與資料可信度

機會地圖：商業成熟度 × 價值取得能力，可依估值狀態篩選
從專利到產品：可點開的技術／公司證據時間軸

本週深研 [重點個案]     待驗證技術 [探索區]     判斷失效 [原因]
資料健康：來源、期間、全文取得、閱讀完成、待讀與失敗
歷史週報／修訂紀錄／研究結果追蹤
```

首頁主內容目標是讓讀者 5 分鐘內了解值得深入研究的幾個方向，點擊後能花 30–60 分鐘讀完整個案。少量且證據完整的候選優於硬湊固定名次；沒有合格候選時明確顯示。

## 2. 頁面與內容

| 頁面 | 必要內容 | 圖表／互動 |
|---|---|---|
| 首頁 `/` | 累積機會、本週變化、兩期限風險、資料截止與品質 | 機會地圖、排序、篩選、變化標記 |
| 技術 `/technologies/{id}/` | 問題、替代方案、成本／效能門檻、專利聚落、商業里程碑、受益與受損公司 | 時間軸、專利家族趨勢、可比較性能曲線、供應鏈圖 |
| 公司 `/companies/{id}/` | 法律實體／證券、營收與產品、技術暴露、財務、估值假設、催化與反證 | 財務趨勢、分部表、估值敏感度、證據時間軸 |
| 專利 `/patent-families/{id}/` | 公開文件、家族、申請人／權利人、權利項摘要、法律狀態和產品假說 | 家族關係、公開／授權時間、相關技術與公司 |
| 風險 `/risks/` | 90／180 天情境、傳導路徑、曝險、觀察門檻與緩和條件 | 風險矩陣、時間序列、地區／供應鏈映射 |
| 週報 `/reports/{year}-W{week}/` | 固定截止點的完整研究、資料清單、分析版本與修訂 | 圖文表格、目錄、列印樣式 |
| 方法與資料 `/methodology/`、`/coverage/` | 評分規則、限制、來源、覆蓋、版本、研究表現 | 來源健康、完成率、預測到期結果 |

穩定 ID 不以公司當前股票代號或可變標題作唯一識別；改名、分拆與週報修訂保持舊連結可用。歷史週報連到當時的論點版本，另提供「查看最新」入口。

## 3. 投資論點卡片

每張卡至少回答：為何值得研究、誰會取得價值、多久能驗證、這週什麼改變、最大反證與當前估值資料是否足夠。

| 欄位 | 內容要求 |
|---|---|
| 論點 | 一句具體主張，不只寫「看好 AI」 |
| 技術與公司 | 技術 ID、法律實體 ID、相關證券，確認關係後顯示 |
| 時間 | 首次建立、最後支持、最後反證、此次更新、下一次檢查 |
| 地位 | 探索／驗證中／持續追蹤／證據增強／降級／失效／資料不足 |
| 成熟與價值 | 技術成熟、商業採用、價值取得、財務承受力分項 |
| 估值 | 所用報價時點、幣別、模型、假設範圍；未做則明示 |
| 正面證據 | 重要性與來源獨立性、日期、引用 |
| 反證 | 已存在的反面資料與替代解釋，不只一般市場風險 |
| 未知 | 哪個缺口會限制結論，下一步取得哪種資料 |
| 否證條件 | 可觀測事件、數值、期限，以及觸發後如何調整 |
| 期限 | 3–10 年里程碑或 90／180 天情境，不能混成同一分數 |

「證據可信度高」表示主張受資料支持的程度，不是股票一定會上漲。研究優先級、技術吸引力與投資價格吸引力分別呈現。

## 4. 每週詳盡報告的固定結構

1. **本週判斷摘要**：最重要的機會、風險與認知變化；直接連結完整論點。
2. **相對上週的變化表**：新增／增強／減弱／失效；列出舊判斷、新判斷及改變證據。
3. **長期技術研究**：重要問題、專利與論文趨勢、成熟門檻、替代路徑、商業化里程碑。
4. **公司研究**：受益方式、業務重要性、競爭者、財務承受力、估值與價格隱含假設。
5. **專利觀察**：新公開／新授權／法律狀態變化，按家族去重，連回原始公開文件。
6. **實體經濟與供應鏈**：貿易、港口、庫存與訂單的異常，季節性與替代解釋。
7. **90 天風險**：事件、金融傳導、敏感產業、短期觀察點、可緩和條件。
8. **180 天風險**：可能延續或逆轉的情境及所需證據，不能直接複製 90 天段落。
9. **反方觀點與失敗紀錄**：本週最有力的反證，哪些舊論點需要撤回。
10. **下一週查證清單**：待公布財報、數據、政策生效日、產品與驗證里程碑。
11. **預測與研究成績**：到期論點、實際結果、基準差異與錯誤原因。
12. **資料與方法附錄**：來源、截止時間、處理狀態、缺漏、模型與規則版本、所有引用。

文章長度隨證據量增減；沒有變化可簡潔延續，不能為「鉅細靡遺」捏造細節。完整性由證據、推理、反證和資料缺口衡量，不以字數驗收。

## 5. 語言與引用規則

繁體中文為主，原文技術名詞、公司法律名稱、專利識別碼保留，首次出現加白話解釋。引用連回原語來源；機器翻譯標明，重要數值、否定詞與條件回原文檢查。

每項內容分成：**已核對事實、來源主張、程式計算、研究推論、情境假設、未知**。例如「公司宣稱成本下降」不能直接改寫為「成本已經下降」。

一個分析段落包含多個事實時，分別附引用。數量成長、營收、報價等有期間、單位與來源；模型計算附輸入與公式版本。引文位置可為章節／段落／頁碼／表格儲存格／JSON pointer／專利 claim number。

原文片段存在只是第一項檢查，還需確認其支持該主張，包含相同公司、期間、單位、範圍和語意。同源轉載只計一次獨立來源。無可核對出處的主張留在待查證區。

## 6. 核心資料契約

以下為欄位設計，不是已實作的 JSON Schema。正式 schema 將鎖定型別、必填欄位、版本和容許的狀態值。

### 證據

```text
evidence_id
document_id / document_version / content_hash
source_id / source_origin_group
published_at / first_seen_at / vintage_at / retrieved_at
locator { kind, section, paragraph, page, table_cell, json_pointer, claim_number }
excerpt / original_language / translation / translation_checked
claim_type: verified_fact | source_statement | calculation | inference | assumption
entity_ids / patent_family_ids / technology_ids
supports_or_refutes / verification_status / coverage_limitations
rights_status / public_export_fields
```

### 論點版本

```text
thesis_id / version / previous_version / title / statement
created_at / as_of / next_review_at / horizon
status / entities / technologies / patent_families
supporting_evidence_ids / opposing_evidence_ids / unresolved_questions
causal_path / alternative_explanations
milestones [{ metric, threshold, unit, deadline, evidence_ids, outcome }]
dimension_assessments [{ dimension, grade_or_unknown, rationale, evidence_ids }]
valuation { status, price_as_of, currency, inputs, scenarios, sensitivity, model_version }
invalidation_conditions / change_reason / change_evidence_ids
analysis_run_id / validator_version / validation_status
```

### 風險與預測

```text
risk_id / forecast_id / as_of / horizon_days / due_at
event_definition / target_region_or_asset / measurement_source
state / likelihood_label / calibrated_probability_or_null
impact / exposed_entity_ids / transmission_path
trigger_conditions / easing_conditions
supporting_evidence_ids / counterevidence_ids
subjective_scenario_weights_or_null / calibration_status
outcome / evaluated_at / evaluation_rule_version
```

`horizon_days` 首版為 90 或 180。機率不可填入研究分數；事件尚未到期或結果資料延遲時不判對錯。情境不是互斥時，不把各情境機率硬湊成 100%。

### 週報與處理狀態

```text
report_id / version / reporting_period / as_of / generated_at
snapshot_frozen_at / decision_available_at
status: draft | partial | validated | published
previous_report_id / supersedes_version / correction_notes
source_manifest_id / analysis_manifest_id / code_version / model_versions
thesis_version_ids / risk_ids / chart_ids / evidence_ids
coverage {
  planned_scope, expected_count_or_unknown, fetched, unique,
  fulltext_available, initial_read_complete, deep_read_eligible,
  deep_read_complete, pending, failed, unavailable, truncated_queries
}
limitations / validation_results / public_manifest_hash
```

文件「讀過」指各可用分段都有處理結果。全文閱讀完成率為完成逐段抽取的文件數除以成功取得全文的唯一文件數；只有初讀不能算進完成數，僅有摘要的文件另報摘要完成率。分母與排除原因可點開檢查。預設所有取得全文皆進入抽取隊列，選用節省模式時另外顯示其篩選方式。

## 7. 圖表設計

| 圖表 | 用來理解什麼 | 必要限制 |
|---|---|---|
| 機會散點圖 | 商業成熟度與價值取得能力 | 研究評級為序位尺度，不冒充精準測量；未知項另列 |
| 技術證據時間軸 | 論文、專利、試產、訂單、收入之間如何演進 | 事件日與資訊公開日可切換；不可在公開前顯示為已知 |
| 專利家族趨勢 | 研發活動是否增加、誰在投入 | 領域／年齡／家族定義／來源覆蓋，低基期提示 |
| 技術效能／成本曲線 | 是否跨過商業門檻 | 相同測試條件與單位；廠商宣稱與獨立測試分開 |
| 公司財務與估值 | 新業務與股東價值是否足夠大 | 重編、幣別、期間、稀釋與假設帶；不畫無數據曲線 |
| 港口與貿易異常 | 哪些地區或商品有實體變化 | 季節性、價格、空重櫃、估計與實測、覆蓋與修訂 |
| 90／180 天風險矩陣 | 各風險方向、影響及可信度 | 兩期限各有依據，無機率時明示 |
| 公司／技術／專利關係圖 | 誰持有、誰供應、誰採用 | 每條邊可點證據，推測與已驗證關係樣式不同 |
| 論點變更與成績圖 | 曾經做出哪些判斷、後來如何 | 保留降級、失效、退市與未到期項，不挑選贏家 |

所有圖表由程式從凍結的資料生成，提供來源、截止日、單位、圖例與可讀表格。折線缺值留空；估計值用不同樣式，區間沒有統計基礎時標情境範圍。圖像生成工具不負責畫帶數值的研究圖，以免產生不存在的資料。

可互動篩選技術、地區、公司、期限和證據狀態；重要圖可匯出 SVG／PNG，提供文字替代說明。手機縮排、表格水平捲動、鍵盤操作、列印樣式及色覺辨識納入驗收。

## 8. 完整論點如何寫：虛構示例

下列只展示格式，不指向真實公司、真實專利或已查證技術；實際網站不得混入研究結果。

| 項目 | 格式示例 |
|---|---|
| 論點 | 某互連技術若在兩個產品週期內達成客戶要求的可靠性與系統成本，相關供應商可能擴大可服務市場 |
| 已取得的證據 | 列出真正讀過的專利權利項、可比較測試、公司申報與客戶確認；此示例尚無 |
| 傳導路徑 | 能耗／頻寬改善 → 特定系統採用 → 供應商單機價值 → 部門收入與利潤 → 整體股東價值 |
| 公司候選 | 只有確認法律實體、權利／供應關係與業務重要性後才列入 |
| 反面解釋 | 既有方案持續降價，或客戶只測試而未採購；供應商競爭壓低利潤 |
| 尚缺資訊 | 良率、量產成本、付費部署、供應商份額、股價與合理估值 |
| 下次檢查 | 下一個可核對的客戶導入或量產里程碑，附日期 |
| 當前狀態 | 只有假說，資料不足，不構成投資候選 |

真實論點的成長情境必須加入證據、數量與敏感度，不能只替換公司名字就視為完成。

## 9. 公開匯出與發布

本機研究資料與網站公開資料採明確白名單匯出。GitHub 只保存專案程式、方法、可公開的自製報告與必要的衍生資料；原始全文、受限制數據、金鑰、CLI 登入檔、模型內部事件紀錄與資料庫不進公開產物。

完整儲存分工與 `latest.json → release manifest → 分片` 的機器讀取介面見 [儲存與發布決策](STORAGE_AND_PUBLISHING.zh-TW.md)。一般原文預設不公開；若是已確認允許再散布的小型原始開放資料，可經白名單另行匯出樣本或資料集，並保留來源與授權。Atlas 可選作本機的查詢副本，網頁只讀靜態產物，不直接連線資料庫。

每來源的授權規則決定可公開內容，即使轉成圖表也要檢查原數據的使用條件；不要認為「做成摘要」就自動取得所有再散布權。公開資料可取用官方來源連結，讀者可回原站查看。

規劃目錄示意，尚未建立：

```text
config/                  來源、主題、公司及分析設定
schemas/                 文件、證據、論點、風險與報告 schema
prompts/                 固定提示詞與版本
src/edgefinance/         採集、解析、研究、驗證與匯出
tests/fixtures/          可合法保存的驗證樣本
site/                    靜態網站程式
public-data/             允許發布的版本化資料
data/raw/                本機原始快照，忽略 Git
data/warehouse/          本機資料庫及時序檔，忽略 Git
work/                    資料包與暫存，忽略 Git
runs/                    執行紀錄與分析結果，忽略 Git
```

來源、排程和 Codex 在本機執行；GitHub Actions 可用於驗證與建置／發布靜態網站。發布流程不需將 ChatGPT 登入狀態放入 GitHub。GitHub Pages 的 project site 需驗證 repository base path、深連結、資源相對路徑和重新整理。[GitHub Pages 靜態網站說明](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages)。

## 10. 發布品質門檻

正式發布前，每次檢查以下項目：

- 每個首頁核心事實都有通過核對的引用，至少涵蓋兩種獨立來源類型；以投資候選呈現者另需非專利商業／財務證據。探索區可較早收錄，但狀態明確。
- 每項數字可由凍結資料與公式重算；若模型與程式計算不一致，返回修正。
- 每個推薦研究論點有期限、反證、未知及否證條件；估值資料不足不宣稱便宜。
- 報告只使用截止前已公開且版本可確認的資料，同時揭露本機凍結及分析可用時間。發布後才取得的補充或更正追加版本；資訊時間不明者不能冒充嚴格時點證據，模擬投資不得早於結果實際可用。
- 公司對應、專利家族與證券沒有已知重大衝突；不確定者留在待查證。
- 無未處理的引用錯配、虛構來源、缺失被填零、混淆幣別／單位／期間。
- 來源故障及初讀／深讀未完成有可見說明；部分報告可以發布，但首頁必須標「部分完成」與限制。
- 本機預覽完成手機／桌機、圖表、表格、連結、搜尋與列印檢查；公開輸出通過憑證與禁止欄位掃描。
- 發布失敗可保留上一版；歷史週報與已公開修訂版本可追溯。

驗證順序：結構與資料規則 → 數值與引用 → 模型反證檢視 → 核心論點人工抽查／覆核 → 網站呈現。模型自評不能取代原文與計算驗證。

回到 [完整專案規劃](PROJECT_PLAN.zh-TW.md) 或 [資料接入清單](DATA_SOURCES.zh-TW.md)。
