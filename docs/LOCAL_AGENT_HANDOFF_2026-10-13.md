# AMVO — 本地 Agent 工程交接主指令

版本：2026-10-13 / v0.1
工程範圍：AMVO 公開 GitHub 儲存庫
Repository：https://github.com/kakon77777-commits/AMVO
優先主文件：本文件、ENGINEERING_MASTER_PLAN_2026-10-13.md、ACCEPTANCE_MATRIX_2026-10-13.md、SOURCE_AND_REVIEW_CONTRACT_2026-10-13.md
文件定位：交接契約與實作任務，不是已完成工作的聲明。

## 0. 給本地 Agent 的直接執行指令

你現在接手 AMVO 的後續工程。請讀取最新公開 main 分支與 AGENTS.md，不要只使用本文件的歷史敘述推論程式已完成。先做完整現況盤點、測試與缺口驗證，再從本文件及 Master Plan 中最高優先的未完成任務向前實作。採用可重現的 commit 與測試證據，避免每次重新寫同一套架構。能安全完成的下一個階段直接實作、測試、提交；不要停留在報告、提問或重複列計畫。

需要外部金鑰、付費 API、公開部署、正式宣稱某篇數學論文驗證成功、法律授權決策或跨儲存庫讀取私人資料時，不得自行假設授權已取得。能做 mock/offline 替代時先完成；需要人工權限者保留阻塞項，不要偽造成功。

以研究成果驗證為核心，不以評論數學家、排行 AI 公司、站隊 OpenAI 或宣傳為工程目標。AMVO 驗證外部公開成果；AMRAL 為姊妹專案，私有資料完全隔離。OCME、SREG、ISQL 只是未來可能的公共介面，不依賴它們就能完成 AMVO。

## 1. 目前已有的工程基線

- Python 標準函式庫離線核心與 CLI。
- Source/Claim/Review/Rights/Checks 基礎 JSON 契約。
- 有理數與多項式係數等式的有限精確檢查；檔案 SHA-256 完整性檢查。
- 公開來源 metadata-only 案例；合成算術測試案例。
- 靜態繁體中文網站，含條目搜尋、狀態篩選與來源連結。
- Windows 一鍵測試／建站腳本；GitHub Actions CI、基本授權與安全文件。
- v0.1.1 新增：數學 claim 必須有聲明的來源版本 pin；支援 git_commit、arxiv_version、sha256。注意：「聲明版本」只是格式檢查，目前尚未真正連線驗證該來源版本或內容。
- 尚未有 Lean/Coq 實際 kernel 重播、全文形式化翻譯驗證、自動抓論文、獨立同行複驗，亦沒有任何外部數學定理由 AMVO 完整認證。

## 2. 本地必須先執行的基礎檢驗

建議環境：Windows + Python 3.11+；正式沙箱工作另外使用 WSL2/Docker，與一般 Windows 主機權限隔離。純基礎版本不依賴雲端 API。

~~~powershell
git clone https://github.com/kakon77777-commits/AMVO.git
cd AMVO
git status --short
git rev-parse HEAD
python -m unittest discover -s tests -v
python -m amvo validate
python -m amvo audit-public
python -m amvo verify --output build/verification.json
python -m amvo build-site --output site
python -m http.server 8000 --directory site
~~~

檢查瀏覽器在 http://localhost:8000 上可展示來源清單、狀態篩選與中文；也要驗證不能將 metadata-only 當成獨立數學驗證。測試數字以實際最新版本為準，不要引用舊交接的 24/24 當作新版本已通過。

### 2.1 若 GitHub Actions 失敗

查明是 runner/billing/policy/permission、依賴、測試、shell 還是網站 build 失敗；報告要附工作流程 URL、run id、失敗步驟與原始訊息。不要將 Actions 執行平台錯誤冒充程式測試失敗，亦不能因本地 PASS 宣稱 CI 已 PASS。

## 3. 直接執行的第一輪任務（P0 → P1）

P0 — 確保主分支可重現：現況檢查、跑測試、CI、基本安全修補，確認 JSON Schema 與 Python runtime 檢查一致，保留正反測試。不得先擴充大量來源導致證據污染。

P1-A — 公開來源穩定性：把已聲明 pin 的來源做真正「受限下載、版本驗證、來源雜湊」；網路依賴明確 opt-in。支援 GitHub 原始 commit、arXiv 指定版本與既有公開存證；實際抓取後只保存必要的 metadata/hash，預設不複製全文。請先做本機 fixtures 與無網路測試，再接真實來源。

P1-B — 修訂與撤回追蹤：建立 immutable evidence/claim lineage（append-only），提供 supersedes/corrects/withdraws/rebuttal 事件，嚴禁悄悄覆蓋原稿。首次只以 synthetic fixtures 測試多版本與衝突。

P1-C — 可檢驗聲明單位：一份論文可以包含多條 theorem、lemma、conjecture，不可用論文總數直接當成已驗證定理數。將來源（Source）、命題（Claim）、形式版命題（Formal Target）、證據（Evidence）、審查（Review）、出版（Publication）分層。

P1-D — 前端報告：顯示原作者／來源版本／最後檢查方式／檢查結果／未知事項／修訂鏈。所有未經真的驗證的項目要顯示 UNKNOWN 或 NOT_CHECKED，不得顯示 VERIFIED。

達成以上、通過 Acceptance Matrix 再進下一階段。若有需要 Lean 的功能，先設計契約與 mock，不要在公開主分支直接執行不受控的外部 proof script。

## 4. 每一輪的工作方式

1. 讀取最新 HEAD 與所有非預期修改，查是否存在其他 Agent 的工作。
2. 只選已定義的最小完備階段，在獨立 feature branch（例如 feat/amvo-source-pinning-replay）實作。
3. 同步補負面測試：錯誤 hash、來源撤回、私有資料、symlink、壞 JSON、惡意引文、非法依賴。
4. 執行 offline test，再執行可選網路 integration test（需要授權與資源上限）。
5. 出具版本 SHA、測試結果、覆蓋與失敗、已知限制、證據路徑、風險與下一個可執行階段。
6. CI PASS 後合併，保留無法完成的 blocked work，不得標示完成。
7. 不要上傳或製作不必要的 ZIP；以 GitHub canonical source 與可重現構建為主。

## 5. 禁止的錯誤宣稱

- GitHub 原稿有 Lean 檔案，不代表 AMVO 已重播證明。
- Lean kernel PASS 不代表自然語言論文原命題忠實映射、沒有依賴漏洞、或是新穎突破。
- AI × AI 多模型一致，不等於獨立數學證明。
- SHA-256 完整性通過，不等於作者證明內容正確。
- 原始研究成果屬於原創者，不因 AMVO 檢查或出版而移轉署名。
- 私有 AMRAL 研究與 EveMissLab 未公開研究不能進 AMVO 公開庫。
- 從使用者眼前的渲染畫面複製公式，不是 canonical source 流程；正式文獻需 UTF-8 原始檔與驗證後的 commit。

## 6. 完成與停工規則

允許在現有 Python 核心穩定之前停止新功能並先修錯。能產出完整最小階段就提交。若需要實機授權或模型 API，完成模擬與契約後列 BLOCKED，保留證據，其他功能照常前進。

最終交付以 GitHub branch / PR / commit URL 為主；文字報告至少含：Scope、Changed Files、Run Commands、Test Counts、Evidence Hashes、Limits、Next Executable Gate。
