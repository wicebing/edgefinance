# GitHub Pages 發布

本機完成研究，GitHub Actions 只發布已整理的靜態資料。

1. Repository 已建立為 `wicebing/edgefinance`，remote 名稱目前是 `edgefinance`。
2. GitHub Settings → Pages → Build and deployment → Source 必須選 **GitHub Actions**；這是 repository 一次性設定。
3. 用 `.venv` 的 Python 執行 `python -m edgefinance validate` 與 `python -m pytest -q`。
4. `git status --short`、`git diff --cached --stat` 檢查提交內容。提交程式、設定、文件、範本、workflow、測試及 `public-data/`；不用 `git add -f` 加入忽略檔。
5. 提交並推送 `main`。工作流程只讀凍結的 `public-data/`，建立 `dist` artifact 後部署。
6. **Verify and publish research** 的 build 與 deploy 都成功後，網址為 `https://wicebing.github.io/edgefinance/`。

先前失敗發生在 `actions/configure-pages` 嘗試用 workflow token 建立 Pages 站點，GitHub 回覆 `Resource not accessible by integration`。目前 workflow 已移除 `enablement: true`；建立或切換 Pages source 由 repository Settings 完成，Action 只負責後續部署。

`src refspec main does not match any` 表示本機 `main` 還沒有第一個 commit。依序執行 `git add -A`、`git commit -m "feat: build EdgeFinance research MVP"`，確認 `git branch --show-current` 為 `main` 後再 push。遠端 repository 不存在或未登入，會是不同的錯誤。

每週：本機 `weekly` → 必要時 `resume` → 閱讀週報 → 提交新 `public-data/` → push。部署驗證所有歷史 manifest，JSON 意外改動會被 hash 檢查攔下。部署成功不代表研究語意已經核准。

## 還原與機器資料

本機前版留在 `data/site-backups/`。GitHub 可重新部署先前成功 commit，或將 `public-data/v1/latest.json` 指向已有且完整的 release 後提交。保留舊週報內容，避免改寫當時判斷。

`public-data/v1/latest.json` → `releases/<report-id>/manifest.json` → `report.json`、`overview.json`、`evidence.json`、`companies.json`、`technologies.json`。

Manifest 有 SHA-256、大小和版本；網頁的同一套資料位於 `data/v1/`。公開證據提供來源 URL、版本、時間、摘要及定位；原文和引文片段留本機。
