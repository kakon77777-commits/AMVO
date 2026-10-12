# AMVO — 工程總計畫 v0.2 → v1.0

版本：2026-10-13
類型：持續更新的工程規格／下一階段研究計畫
狀態：待本地 Agent 分階段實作
Maintainer：EveMissLab
Canonical：GitHub 原始 UTF-8 Markdown

## 1. 核心使命

AMVO（AI Mathematics Verification Observatory）是「外部公開 AI 數學成果」的獨立來源、重現、形式驗證、異議審計、出版報導平台。它不是學術期刊、不是原成果的作者，不是對陶哲軒/AHM/OpenAI 的立場網站，也不是 AMRAL 自主研究主系統。

成功標準是：第三方能查到原始命題、來源版本、實際重算方法、正反證據、已驗與未驗項目，能在授權環境依文件重現 AMVO 的特定檢查。

AMVO 必須可以在不重新訓練任何專用數學基座模型的情況下運作。自主 research-agent 模式可以接前沿通用模型，也可以接開放模型，但都只是替換式 provider。模型產生結果永遠先進 candidate，不是 theorem authority。

## 2. 系統分層與責任界面

A — Source Intake：搜尋與登錄公開資料。證據只含來源與版本，不得聲稱數學正確性。
B — Provenance：pin、原文快照 hash、來源/使用許可、immutable revision history。
C — Claim Registry：抽出精確定理、條件與量詞，映射原文件段落，拆分獨立命題。
D — Verification Planner：根據命題類型選出最小有效檢查、計算上限、所需工具。
E — Verification Executors：Python 精確算術、符號運算、Lean/Coq/Isabelle，以及獨立 checker；所有外部工具均隔離。
F — Semantic Audit：檢查自然語言與形式化 target 是否同一命題，避免 stronger-assumption / weaker-conclusion。
G — Independent Review：以不同模型與不同數學路徑尋找反例、依賴錯誤與未公開假設。
H — Evidence/Authority：簽章、hash、覆核、不變量、禁止未授權權限升格。
I — Publication/API：網站、機器可讀 API、月刊、公開研究報導。
J — Governance：署名、研究衝突、法律權利、撤回與異議處理。

建立每層獨立的儲存格式；不因下游需求直接污染上游 canonical data。

## 3. 建議資料模型

Source：source_id, title, publisher, author_ids, canonical_url, public_state, retrieved_at, license_evidence, origin_type。
SourceRevision：revision_id, source_id, pin_kind, pin_value, content_sha256, bytes, capture_time, remote_verified, version_label。
Claim：claim_id, revision_id, textual_statement, quantifiers, assumptions, scope, claim_type, parent_claim_ids。
FormalTarget：formal_target_id, claim_id, theorem_name, exact_statement, code_revision, toolchain_lock, axiom_policy。
Evidence：evidence_id, claim_id, check_kind, input_hash, environment_hash, command_hash, result_hash, bounded_claim, execution_status, execution_timestamp。
Review：review_id, claim_id, reviewer_class, conflict_disclosure, assessment_scope, audit_state, references。
CorrectionEvent：event_id, target_id, event_type, supersedes_id, signed_by, rationale, recorded_at。
PublicationProjection：publication_id, source_evidence_ids, selected_claims, editorial_checks, license_review_state, revision_id。

以上是下一代邏輯資料模型；v0.1.1 仍為單一 JSON Case，請設計 migration，不可突然刪除舊格式。可以先 SQLite（標準函式庫）記錄索引，再決定是否需要 PostgreSQL。Immutable 事件表和來源資料不可覆寫。

關鍵硬規則：FormalTarget 與自然語言 Claim 必須有明確對應；Evidence 不可反向更改 Claim；Review 不能修改原始來源；Publication 不能冒充 Evidence。

## 4. 工作階段

### Phase 0 — 可重現基線與安全

入口：公開 main HEAD。
交付：環境鎖、offline full tests、CI、JSON Schema/runtime 一致性、版權/隱私檢查、Windows 一鍵執行確認。
必要負測試：未授權 repo、URL with credentials、非 HTTPS、私有/本地 IP、目錄穿越、symlink、錯誤數值、重複 ID、惡意 HTML/XSS。
退出：完整測試證據、成功 CI、已知問題清單。

### Phase 1 — 外部來源版本化與更新

不以大量下載整批論文為目標。先挑「10 個公開、清楚授權、有明確版本、類型不同」的來源做 metadata-only；大部分可先只保留 URL 與 pinned hash。無法確定來源授權則只存 metadata，不鏡像原稿。

按 source_id 區分不同供應方。支援：公開 Git commit 固定版；arXiv 具 vN 版本論文；公開發布 hash。來源抓取只在人工顯示許可的 allowlist 下執行，禁止任意 URL 抓取到內網。
遠端 pin 驗證、文件 fingerprint、來源撤回通知、同一來源的新舊版比較都需保留清楚記錄。
退出：source fixture 遷移、版本更新保留前版、至少一組真實外部來源的可重現元資料取得流程（不必複製原文）。

### Phase 2 — 命題級資料與修正帳本

一篇文獻可包含多個 result family / theorem / lemma / claim。拆解命題採候選生成 + 人工或可驗證策略批准，保留引用段落與原稿版本。
撤回、修訂、反例與補證明使用 append-only events；不能偷偷修改 case 判定。
退出：不同命題與來源一對多、多對一依賴圖；withdrawn 未被 UI 解讀成「當前已證」。

### Phase 3 — 確定性驗證引擎

在 v0.1.1 算術基礎上，新增 SymPy（僅明確允許的操作）、有理數矩陣、精確多項式、有界數值精度比較與反例搜尋，但需描述數值誤差與輸入域。
任何數值結果須標出精度、容忍、網格、來源、假設。禁止把 finite sample 直接當 universal proof。
退出：所有 pass/fail/error/unknown 都可重播，且 no theorem auto-promotion。

### Phase 4 — Lean 4 真實 Kernel Runner（最高安全要求）

採外部獨立 worker，先用合成 Lean 例子打通，固定 Lean 4、mathlib、依賴、OS image digest。
Sandbox：禁預設網路、只讀 root filesystem、隔離 host credentials、CPU/RAM/時間/輸出大小限制、無 privileged、無 Docker socket、不可取得 GitHub write token。
記錄：theorem text、精確 import、Lean 版本、依賴 hash、axiom 列表、sorry/admit/unsafe/aesop 使用狀況、命令、退出碼、檢查輸出 hash。
Lean compiler PASS 只能聲稱「該 formal target 在記錄的環境通過」。原始自然語言 theorem 是否一樣，要由 Phase 5 審計。

### Phase 5 — 語義一致性、第三方獨立複驗

對 source Claim vs FormalTarget 建立量詞、假設、域、邊界條件、存在性/全稱性、結論強度、正向/逆向推理對照。
多模型交叉質疑須披露模型版本和共享依賴；兩個同基座模型一致不是獨立證明。
引入「可反駁的異議物件」：指出哪條 lemma、不等式、強化假設、counterexample、文獻優先權出現問題。
先用已知含有錯誤或不完整證明的測試集，驗證系統能否阻止錯誤升格。
退出：至少一組第三方可重播的限定 scope 證據報告；不要求 Clay 等開放問題被解決。

### Phase 6 — 公開觀測站與 API

網站按 Case/Claim/Source/Revision 分別查詢，永遠顯示來源作者、證據等級、異議、最後檢查版本、工具環境。
只允許安全文本呈現，不渲染未經清理的來源 HTML，避免XSS。資料應分 static release 和動態 ingestion；不得公開 private queues。
可選 REST API read-only，支援 versioned schema、ETag/hash、pagination、rate-limit、accessibility。先維持免費靜態站。

### Phase 7 — AMRAL/OCME/SREG/ISQL 的姊妹整合

僅透過顯式可審查的 PUBLIC EXPORT 接口互通。OCME 訓練語料以既有數學為主；不要將未公開 EveMissLab 原創理論混入。SREG 可作 verifier provider，ISQL 可作 representation adapter，但必須先完成與 baseline 的實驗對照才有能力聲稱提升。
AMRAL → AMVO 不能自動公開原稿、內部 prompt、私有 source 等。AMVO → AMRAL 也只能將明確授權與標註的公開已檢查材料輸出，避免污染測試集。

### Phase 8 — 自主 Agent/MCP 研究作業

採 Planner、Collector、Prover、Verifier、Critic、Provenance、Editor 等角色，但權限獨立。
研究狀態 Candidate → Checked → Reviewed → Publishable → Published；任何非證明資料不能自動升格。
限時、限 token、限 API 預算、失敗退回、客觀退出門檻；不要讓 agent 幻覺「已完成」。第一次只 offline mock，之後接實際 API。
Agent 的目標是提升獨立驗證效率，不能替代 kernel 或資深數學審查的證據責任。

### Phase 9 — 雜誌／AI 公關出版投影

為公開驗證材料產生科普摘要、技術版、版本異動、爭議整理與編輯可追溯引文。
雜誌是獨立出版投影，不是學術期刊，不得把未證新結果寫成已解。
每篇出版物附：原作者/原源連結、驗證範圍、仍未知、修訂日期、授權資訊。
Amazon 出版需另外核實當期發行規則和 AI 生成內容政策，不預設一定接受月刊。

## 5. 建議優先順序與成本

P0（立刻）：CI/安全，版本 pin 真實核對，JSON Schema/runtime 一致性，修訂事件；不花 API 錢。
P1（有穩定本地環境）：Lean isolated worker 和自然語言語義契約的 mock；優先重現 synthetic/已知數學，不碰高風險遠端任意執行。
P2（具備有限預算）：加入 1–2 家 provider 比較，多模型驗證流程，按有效驗證／美元衡量。
P3（公開已有獨立案例）：網站、領域索引、出版、合作與導入來源擴張。

不需要從頭訓練數學基座模型。先證明多模型自主研究與獨立驗證「可持續運行」且成本受控。專用模型可作可替換元件而非必需前提。

## 6. 成果計量原則

分別統計：文件數、來源數、命題數、已跑有界檢查、已通過形式 kernel、完成語義對照、獨立複驗、撤回、修訂、未解異議。
不可把它們合併成「驗證論文總數」。不能用 GitHub Actions 測試通過或數學引理數推論整套研究可證原始開放命題。

## 7. 驗證／提交契約

每次 commit/PR 必須列出：base/head commit、source/evidence fingerprints、測試命令與結果、哪一項現實資料經重新取得、哪一項只為 fixture、benchmark 成本、未驗證事項。
關鍵安全和數學證據閘門通過後才 merge 到 main。
最終出品保存 UTF-8 canonical source，不以渲染對話為正式數學原稿。
