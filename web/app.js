"use strict";

// No third-party scripts, analytics, model API calls, or use of innerHTML.
// Renders data/index.json -> registry (the layered v0.2 report). Every claim states what was
// actually computed about it; anything not checked reads NOT_CHECKED or UNKNOWN, never VERIFIED.
const $ = (id) => document.getElementById(id);

// claim statuses from the report; tone only picks a colour
const STATUS = {
  NOT_CHECKED: { text: "尚未檢查", tone: "neutral", note: "沒有任何 AMVO 檢查涉及這條命題。" },
  REPRODUCIBILITY_ONLY: { text: "僅工件雜湊相符", tone: "neutral", note: "只確認某個檔案的位元組與聲明的 SHA-256 相同；不涉及數學內容。" },
  BOUNDED_PASS: { text: "有限檢查通過", tone: "pass", note: "列出的有限、確定性計算確實成立；不是一般性證明。" },
  CHECKS_NOT_PASSED: { text: "檢查未通過", tone: "fail", note: "至少一項 AMVO 檢查沒有通過或無法執行。" },
  SEMANTIC_ALIGNMENT_PENDING: { text: "語義對齊未評估", tone: "neutral", note: "已有形式化目標，但它是否忠實對應原命題尚未評估。" },
  INDEPENDENT_REPLICATION_PENDING: { text: "尚無獨立複核", tone: "neutral", note: "沒有獨立數學審查者在其範圍內提出「無異議」。" },
  OBJECTION_OPEN: { text: "有未結異議", tone: "fail", note: "有已記錄的異議或反例，尚未處理。" },
  SUPERSEDED: { text: "已被新版取代", tone: "history", note: "有更新的紀錄取代它；舊結果保留作歷史。" },
  WITHDRAWN: { text: "已撤回", tone: "history", note: "來源或其版本已撤回；舊結果保留作歷史，不算現行結果。" },
  PUBLISHED_REPORT: { text: "已有公開報告", tone: "neutral", note: "有公開報導引用它；報導不是驗證。" }
};
const UNKNOWN_STATUS = { text: "未知狀態", tone: "fail", note: "" };

// source pin states; only a live, matching capture reads as checked
const PIN_STATES = {
  verified: "已向原始來源核對版本",
  declared_only: "僅為聲明，未向原始來源核對",
  no_pin: "合成測試來源，沒有固定版本",
  fixture_only: "僅有測試夾具重放，不算核對",
  mismatch: "原始來源回報的版本與聲明不符",
  not_found: "原始來源查無此版本",
  unavailable: "未能連上原始來源（不視為通過）",
  unsupported: "此類版本目前無法向來源核對",
  capture_invalid: "核對紀錄無效"
};
const CHECK_RESULT = { pass: "PASS", fail: "FAIL", error: "ERROR" };
const EVENT_TYPES = { withdraws: "撤回", supersedes: "取代", corrects: "更正", rebuttal: "異議" };
const REVIEWERS = { amvo_maintainer: "AMVO 維護者", independent_mathematician: "獨立數學審查者",
  original_author: "原作者", automated_tool: "自動化工具" };

let claims = [];

function el(tag, css, value) {
  const node = document.createElement(tag);
  if (css) node.className = css;
  if (value !== undefined) node.textContent = String(value);
  return node;
}

function safeUrl(url) {
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "https:" || parsed.username || parsed.password) return null;
    return parsed.href;
  } catch (_) {
    return null;
  }
}

function link(text, url) {
  const href = safeUrl(url);
  if (!href) return el("span", "", text);
  const a = el("a", "", text);
  a.href = href;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  return a;
}

function captureDate(name) {
  const s = String(name || "");
  return /^[0-9]{8}T/.test(s) ? s.slice(0, 4) + "-" + s.slice(4, 6) + "-" + s.slice(6, 8) : "";
}

function fact(list, term, ...values) {
  list.append(el("dt", "", term));
  const dd = el("dd");
  for (const v of values) dd.append(typeof v === "string" ? document.createTextNode(v) : v);
  list.append(dd);
  return dd;
}

function pill(code) {
  const s = STATUS[code] || UNKNOWN_STATUS;
  const node = el("span", "pill " + s.tone, s.text);
  node.title = code;
  return node;
}

function pinText(rev) {
  if (!rev) return "UNKNOWN";
  const state = PIN_STATES[rev.pin_status] || "UNKNOWN";
  const checked = rev.pin_verified === true && rev.pin_status === "verified";
  const when = checked && captureDate(rev.pin_capture) ? "（" + captureDate(rev.pin_capture) + "）" : "";
  const pin = rev.pin ? rev.pin.kind + " · " + rev.pin.value.slice(0, 12) + (rev.pin.value.length > 12 ? "…" : "") + " · " : "";
  return rev.version_label + " · " + pin + state + when;
}

// the type word is the source's own label only when the location names the numbered heading it was quoted under;
// otherwise it is AMVO's classification and says so
function claimKind(c) {
  const type = c.claim_type || "other";
  const word = type.charAt(0).toUpperCase() + type.slice(1);
  const labelled = (c.location || "").split(", ").some((part) => part.startsWith(word + " "));
  const basis = labelled ? "原稿標示：" + word : "AMVO 歸類：" + type + "（非原稿標示）";
  const checked = c.statuses.includes("NOT_CHECKED") ? "未檢查" : "已有檢查，見下";
  return basis + " · " + checked + (c.location ? " · " + c.location : "");
}

function makeClaim(c, ctx) {
  const card = el("article", "claim");
  const header = el("div", "record-header");
  header.append(el("span", "record-id", c.id));
  const pills = el("div", "pills");
  for (const code of c.statuses) pills.append(pill(code));
  header.append(pills);
  card.append(header);

  card.append(el("p", "claim-kind", claimKind(c)));
  card.append(el("h3", "statement", c.statement));
  card.append(el("p", "scope", "範圍：" + c.scope));

  const src = ctx.sources.get(c.source);
  const rev = ctx.revisions.get(c.revision);
  const facts = el("dl", "facts");
  fact(facts, "原作者", src ? src.authors.join("、") + " · " + src.publisher : "UNKNOWN");
  fact(facts, "來源", src ? link(src.title + " ↗", src.canonical_url) : "UNKNOWN");
  const pinDd = fact(facts, "來源版本", pinText(rev));
  if (rev && rev.pin_verified === true && rev.pin_status === "verified") pinDd.className = "ok";
  else if (rev && rev.pin_status !== "declared_only" && rev.pin_status !== "no_pin") pinDd.className = "warn";

  const checks = el("ul", "plain");
  if (!c.evidence.length) checks.append(el("li", "", "NOT_CHECKED — 尚無任何 AMVO 檢查"));
  for (const e of c.evidence) {
    const li = el("li");
    li.append(el("span", "code " + (e.result === "pass" ? "ok" : "warn"), CHECK_RESULT[e.result] || "UNKNOWN"));
    li.append(document.createTextNode(" " + e.kind + " — " + e.bounded_claim));
    checks.append(li);
  }
  fact(facts, "檢查方式與結果", checks);
  fact(facts, "重算者", ctx.engine + "（建置網站時重算；不是人工審查）");

  const unknown = el("ul", "plain");
  unknown.append(el("li", "", "形式化核心：NOT_RUN — 本引擎不執行任何證明檢查器"));
  unknown.append(el("li", "", c.formal_targets.length
    ? "語義對齊：UNKNOWN — 有 " + c.formal_targets.length + " 個形式化目標，對應是否忠實尚未評估"
    : "語義對齊：NOT_CHECKED — 尚無形式化目標"));
  if (!c.reviews.length) unknown.append(el("li", "", "獨立數學審查：NOT_CHECKED"));
  for (const r of c.reviews) {
    unknown.append(el("li", "", "審查：" + (REVIEWERS[r.reviewer_class] || "UNKNOWN") + " · " + r.audit_state + "（" + r.id + "）"));
  }
  unknown.append(el("li", "", "新穎性與文獻定位：UNKNOWN"));
  unknown.append(el("li", "", "原命題一般是否成立：UNKNOWN — AMVO 不認證外部定理"));
  fact(facts, "未知事項", unknown);

  const related = new Set([c.id, c.revision, c.source].concat(c.legacy_records || []));
  const chain = ctx.events.filter(ev => related.has(ev.target) || related.has(ev.by));
  const chainList = el("ul", "plain");
  if (!chain.length) chainList.append(el("li", "", "無撤回、取代、更正或異議紀錄"));
  for (const ev of chain) {
    const li = el("li");
    li.append(el("span", "code", ev.event_id));
    li.append(document.createTextNode(" " + (EVENT_TYPES[ev.type] || "UNKNOWN") + " · " + ev.recorded_at.slice(0, 10)
      + " · " + ev.target + (ev.by ? " → " + ev.by : "") + " — " + ev.rationale + " "));
    if (ev.source_url) li.append(link("出處 ↗", ev.source_url));
    chainList.append(li);
  }
  fact(facts, "修訂鏈", chainList);
  card.append(facts);

  if (c.legacy_records && c.legacy_records.length) {
    card.append(el("p", "scope", "由 v0.1 紀錄遷移：" + c.legacy_records.join("、")));
  }
  const group = ctx.groups ? ctx.groups[c.id] : null;
  if (group) card.append(makeGroup(group, ctx));
  return card;
}

const TYPE_WORDS = { theorem: "定理", proposition: "命題", corollary: "推論", lemma: "引理", conjecture: "猜想" };

// statements filed under this claim live in their own file and are fetched only when asked for
function makeGroup(group, ctx) {
  const box = el("div", "group");
  const parts = Object.keys(group.by_type).sort().map(t => (TYPE_WORDS[t] || t) + " " + group.by_type[t]);
  box.append(el("p", "scope", "稿件中逐字引出的敘述：" + group.count + " 條（" + parts.join(" · ") + "），每條都未檢查。"));
  const button = el("button", "load-group", "載入這 " + group.count + " 條敘述");
  button.type = "button";
  const list = el("div", "claim-list nested");
  button.addEventListener("click", async () => {
    if (!/^claims\/[a-z0-9-]+\.json$/.test(group.file)) return;     // only our own generated files
    button.disabled = true;
    button.textContent = "讀取中…";
    try {
      const response = await fetch("./data/" + group.file, { cache: "no-store" });
      if (!response.ok) throw new Error("HTTP " + response.status);
      const data = await response.json();
      list.replaceChildren();
      for (const child of data.claims || []) list.append(makeClaim(child, ctx));
      button.remove();
    } catch (error) {
      button.disabled = false;
      button.textContent = "讀取失敗，再試一次";
    }
  });
  box.append(button);
  box.append(list);
  return box;
}

function makeSource(s, ctx) {
  const card = el("article", "record");
  const header = el("div", "record-header");
  header.append(el("span", "record-id", s.id));
  header.append(el("span", "pill neutral", s.origin_type));
  card.append(header);
  card.append(el("h3", "", s.title));
  card.append(el("p", "", s.authors.join("、") + " · " + s.publisher));
  const revs = ctx.report.revisions.filter(r => r.source === s.id);
  const n = ctx.report.claims.filter(c => c.source === s.id).length;
  const list = el("ul", "plain");
  if (!revs.length) list.append(el("li", "", "尚無固定版本：只記錄了來源本身"));
  for (const r of revs) list.append(el("li", r.pin_verified ? "ok" : "", pinText(r)));
  card.append(list);
  card.append(el("p", "scope", "已登錄命題：" + n + " 條" + (n ? "" : "（來源已登錄，不代表其中任何命題已被檢查）")));
  card.append(el("p", "scope", "授權：" + s.rights.mode + " — " + s.rights.note));
  const footer = el("div", "record-footer");
  footer.append(link("原始來源 ↗", s.canonical_url));
  card.append(footer);
  return card;
}

function matches(c, filter) {
  const current = c.lineage.state === "current";
  if (filter === "all") return true;
  if (filter === "current") return current;
  if (filter === "history") return !current;
  return current && c.statuses.includes(filter);
}

function update(ctx) {
  const text = $("search").value.trim().toLocaleLowerCase();
  const filter = $("status").value;
  const list = $("claims-list");
  list.replaceChildren();
  const found = claims.filter(c => {
    if (!matches(c, filter)) return false;
    const src = ctx.sources.get(c.source);
    const hay = [c.id, c.statement, c.scope, c.source, src ? src.title : "", src ? src.authors.join(" ") : "",
      src ? src.publisher : ""].join(" ").toLocaleLowerCase();
    return hay.includes(text);
  });
  for (const c of found) list.append(makeClaim(c, ctx));
  $("load-status").textContent = found.length === 0 ? "目前沒有符合條件的命題。" : "";
}

async function init() {
  try {
    const response = await fetch("./data/index.json", { cache: "no-store" });
    if (!response.ok) throw new Error("HTTP " + response.status);
    const data = await response.json();
    const report = data.registry;
    if (!report || report.report_schema !== "0.2") throw new Error("no layered report");
    const ctx = {
      report,
      engine: String(report.engine || "UNKNOWN"),
      sources: new Map(report.sources.map(s => [s.id, s])),
      revisions: new Map(report.revisions.map(r => [r.id, r])),
      events: data.events || [],
      groups: report.claim_groups || {}
    };
    claims = report.claims;
    const n = report.counts;
    $("n-sources").textContent = n.sources;
    $("n-claims").textContent = n.claims;
    $("n-bounded").textContent = n.current_claims_bounded_pass;
    $("n-unchecked").textContent = n.current_claims_not_checked;
    $("n-kernel").textContent = n.formal_kernel_runs;
    $("n-proved").textContent = n.theorems_proved;
    $("engine").textContent = "AMVO · EveMissLab · " + ctx.engine;
    const sources = $("sources-list");
    for (const s of report.sources) sources.append(makeSource(s, ctx));
    const legend = $("legend");
    for (const [code, s] of Object.entries(STATUS)) {
      const dt = el("dt");
      dt.append(pill(code));
      dt.append(el("span", "code", code));
      legend.append(dt);
      legend.append(el("dd", "", s.note));
    }
    $("search").addEventListener("input", () => update(ctx));
    $("status").addEventListener("change", () => update(ctx));
    update(ctx);
  } catch (error) {
    $("load-status").textContent = "無法讀取公開資料。請先執行 python -m amvo build-site，再透過 HTTP server 開啟；不要直接以 file:// 開啟。";
  }
}
init();
