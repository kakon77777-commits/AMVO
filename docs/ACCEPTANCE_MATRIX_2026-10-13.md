# AMVO — 品質驗收矩陣與反例測試契約

版本：2026-10-13
性質：本地 Agent 後續開發的可執行品質閘門

## A. 不變量（每個 Phase 都必須保持）

| ID | 不變量 | 失敗判準 |
| --- | --- | --- |
| T01 | Source Intake 不等於數學證明 | 任意公開來源自動顯示 theorem_verified |
| T02 | Hash matching 不等於證明正確 | file_sha256 PASS 自動升格論文真偽 |
| T03 | 有界算式不能升格全稱定理 | 一個 finite check 變成 universal-proof verdict |
| T04 | Lean kernel 實際未執行就不得標為已跑 | mock/編譯計畫當成 genuine formal replay |
| T05 | Lean PASS 不自動等於 Claim/FormalTarget 對齊 | 無語義對照即宣稱自然語言原命題成立 |
| T06 | 每條 claim 可追到固定來源版本 | source revision 可默默變動或更新未記錄 |
| T07 | 修訂／撤回不可抹除舊事件 | correction 覆寫證據歷史 |
| T08 | public repo 不得拿私有來源補料 | AMRAL/私有論文直接進 AMVO |
| T09 | 第三方著作權獨立於 AMVO MIT | 視 MIT 為鏡像所有外部論文的權限 |
| T10 | Claim、Review、Publication 權限分離 | Editor 能自行偽造 proof verdict |
| T11 | 失敗/未知不得變 PASS | Runner 不可用、模型超時、依賴缺失被當成功 |
| T12 | 可重現性與版本相依 | 重播缺 toolchain/commit/hash/輸入 |

## B. v0.1.1 最新基線

| Gate | 最小命令／檢查 | 期待 |
| --- | --- | --- |
| B01 | python -m compileall -q amvo tests | 完整編譯通過 |
| B02 | python -m unittest discover -s tests -v | 100% pass；記錄實際 count |
| B03 | python -m amvo validate | 合法的公開 fixtures 載入 |
| B04 | python -m amvo audit-public | 目前未發現機密格式；不宣稱全面隱私安全 |
| B05 | python -m amvo verify --output build/verification.json | report deterministic，無外部 theorem proved |
| B06 | python -m amvo build-site --output site | HTML / CSS / JS / JSON 存在，瀏覽器讀取正常 |
| B07 | GitHub Actions | 該提交對應工作流程 PASS，失敗則具體記錄 |
| B08 | git status --short | 無未預期修改或私有檔 |

## C. Phase 1 來源 pin / metadata 的測試

| ID | 輸入 | 必須輸出 |
| --- | --- | --- |
| S01 | 公開 Git commit 40 hex | 格式接受，未連線前顯示 only declared |
| S02 | 公開 Git commit 64 hex | 格式接受，未連線前顯示 only declared |
| S03 | 分支 main/latest 假冒固定版本 | REJECT |
| S04 | arXiv 2610.12345v2 | 格式接受；需遠端核對才算來源 pin 確認 |
| S05 | arXiv 無 vN | REJECT 作為 immutable claim pin |
| S06 | 正確 SHA-256 結構 | 接受聲明；未實際讀檔前不得列內容 hash 已核對 |
| S07 | 壞 URL、憑證、query token、localhost/private IP | REJECT |
| S08 | Source 含不公開或未知多餘欄位 | REJECT，不寫入報告 |
| S09 | claim 無 pin | REJECT；metadata-only 可以暫時未 pin |
| S10 | 來源已被撤回 | 保留舊版，但 UI 顯示 withdrawn |
| S11 | 同一 source 有新版本 | 新 revision，保留舊 hash/時間/異議 |
| S12 | 公開來源資料庫失聯 | UNKNOWN/UNAVAILABLE，不能自動變 PASS |

## D. Phase 2–4 樣本/形式化測試

| ID | 情境 | 驗收 |
| --- | --- | --- |
| V01 | 有理數真等式 | finite exact PASS；theorem_proved=false |
| V02 | 有理數假等式 | bounded FAIL |
| V03 | 多項式係數有尾零 | 規範化後結果正確 |
| V04 | division by zero | 安全拒絕 |
| V05 | evidence 路徑穿越、symlink | 安全拒絕，無 host 泄漏 |
| V06 | evidence checksum mismatch | FAIL，不改寫 expected hash |
| V07 | proof script 包含 sorry/admit | 不得 formal-certified |
| V08 | proof script 引入未審核新公理 | 阻止升格 |
| V09 | Lean version/mathlib 不一致 | INCOMPATIBLE / UNKNOWN |
| V10 | Lean 形式定理較自然語言弱 | semantic alignment FAIL 或 REVIEW_REQUIRED |
| V11 | Lean 形式定理比自然語言假設更強 | semantic alignment FAIL 或 REVIEW_REQUIRED |
| V12 | Lean compiler timeout | UNKNOWN，不是 theorem false |
| V13 | 兩模型同意，但共享依賴且缺 kernel | 保留 candidate，不升格 |
| V14 | Known wrong theorem 反例可重建 | 正確記錄 counterexample 和來源 |
| V15 | 引用已有定理但稱新發現 | novelty unresolved，保留原作者貢獻 |
| V16 | 自然語言/LaTeX 轉寫變化 | 不修改 canonical source，diff 可見 |

## E. Phase 5–9 出版與治理

| ID | 標準 | 必須有的證據 |
| --- | --- | --- |
| P01 | 研究來源可追溯 | 原作者、URL、公開版本、核查時間 |
| P02 | 署名分層 | Original/Checker/Reviewer/Editor/AI role |
| P03 | 校對負面訊息 | 更正與撤回和原結果同樣可見 |
| P04 | 公開網站安全 | XSS、CSP、不可執行外源內容 |
| P05 | AI 公關未捏造發現 | 每個肯定句都有 evidence id |
| P06 | 論文數不等於已驗證數 | 分類統計符合真實結果 |
| P07 | 私有資料隔離 | 測試能阻擋 private import，檢查 git history |
| P08 | 可重現與採樣成本 | 狀態、工具版本、預算、退出碼、檢查 hash |
| P09 | 研究治理中立 | 相同標準適用於所有 AI 公司與數學家 |
| P10 | 宣傳內容不等於學術期刊 | 編輯版須明確區分 journal、magazine 與 evidence |

## F. 每輪驗收產物

1. 原始 commit 和 PR URL（或明確的本地待提交狀態）。
2. tests PASS/FAIL/ERROR/SKIP 數量，不得推測。
3. 新增/修改 source schema 的版本與 migration。
4. 產生的驗證證據與 SHA-256。
5. 不符合條件的反例清單（若有）。
6. 安全、授權、獨立性與語義對照尚未解決事項。
7. 下一個具體可執行階段。

不得以「全部做完」取代上述實證。
