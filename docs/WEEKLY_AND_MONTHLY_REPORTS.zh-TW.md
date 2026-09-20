# 每週研究與每月專刊

每週在本機執行：

```powershell
.\.venv\Scripts\python.exe -m edgefinance weekly
.\.venv\Scripts\python.exe -m edgefinance status
.\.venv\Scripts\python.exe -m edgefinance validate
.\.venv\Scripts\python.exe -m edgefinance serve
```

`weekly` 先更新公開來源與專利批次，再由 Codex CLI 逐段抽取有原文引用的事實，最後綜合長期機會和 14／30／90／180 天風險。分析任務最多三份並行，每份仍獨立驗證逐字引文；來源逾時、訂閱用量或每次上限造成的待處理量會保留，下次用 `resume` 接續。

每份週報都是凍結版本。新報告依技術主題或共同公司搜尋過去 12 期，標示新論點、延續追蹤或論述更新，並連回原週報。相同日期的重建視為修訂版本，不拿來冒充新的週間觀測。

每月 1–7 日執行時，系統會用目前證據量和歷史週報重複出現的主題選題。專刊至少包含三個證據章節、可能取得價值的觀察公司、反方論點、12 個月及 3–10 年里程碑、否證與下一步。每個章節引用既有證據 ID；證據不足時不生成專刊。

本機預覽確認後提交 `public-data/v1/` 與程式碼。GitHub Actions 只驗證已凍結的公開資料並部署靜態網站，不會在雲端使用 Codex、API 帳密或 MongoDB。
