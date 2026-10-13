"use strict";

// No third-party scripts, analytics, model API calls, or use of innerHTML.
const $ = (id) => document.getElementById(id);
const LABELS = {
  not_checked: "尚無檢查",
  bounded_checks_pass: "有限檢查通過",
  checks_not_passed: "檢查未通過"
};
// source_pin_status from the report; a version check is about which source, never about the mathematics
const PIN_STATES = {
  verified: { text: "已向原始來源核對版本" },
  declared_only: { text: "僅為聲明，未向原始來源核對" },
  fixture_only: { text: "僅有測試夾具重放，不算核對", warn: true },
  mismatch: { text: "原始來源回報的版本與聲明不符", warn: true },
  not_found: { text: "原始來源查無此版本", warn: true },
  unavailable: { text: "未能連上原始來源（不視為通過）", warn: true },
  unsupported: { text: "此類版本目前無法向來源核對", warn: true },
  capture_invalid: { text: "核對紀錄無效", warn: true }
};
let entries = [];

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

function makeRecord(item) {
  const record = item.record;
  const result = item.result;
  const card = el("article", "record");
  const header = el("div", "record-header");
  header.append(el("span", "record-id", record.id));
  const label = el("span", "pill" + (result.outcome === "bounded_checks_pass" ? " pass" : result.outcome === "checks_not_passed" ? " fail" : ""), LABELS[result.outcome] || "未知");
  header.append(label);
  card.append(header);
  card.append(el("h3", "", record.title));
  card.append(el("p", "", record.claim.statement));
  card.append(el("p", "scope", "範圍：" + record.claim.scope));
  const footer = el("div", "record-footer");
  footer.append(el("span", "", record.source.publisher + " · " + record.source.version));
  if (record.source.pin) {
    const pin = record.source.pin;
    const state = PIN_STATES[result.source_pin_status] || PIN_STATES.declared_only;
    // only a live, matching capture is shown as checked; everything else says what it is not
    const checked = result.source_pin_verified === true && result.source_pin_status === "verified";
    const stamp = checked ? String(result.source_pin_capture || "") : "";
    const when = /^[0-9]{8}T/.test(stamp) ? "（" + stamp.slice(0, 4) + "-" + stamp.slice(4, 6) + "-" + stamp.slice(6, 8) + "）" : "";
    footer.append(el("span", "source-pin" + (checked ? " verified" : state.warn ? " warn" : ""),
      "來源版本：" + pin.kind + " · " + pin.value.slice(0, 12) + "… · " + state.text + when));
  }
  const url = safeUrl(record.source.url);
  if (url) {
    const link = el("a", "", "原始來源 ↗");
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    footer.append(link);
  }
  card.append(footer);
  return card;
}

function update() {
  const text = $("search").value.trim().toLocaleLowerCase();
  const filter = $("outcome").value;
  const list = $("records-list");
  list.replaceChildren();
  const found = entries.filter(({record, result}) => {
    if (filter !== "all" && result.outcome !== filter) return false;
    const haystack = [record.title, record.id, record.source.publisher, record.claim.statement]
      .join(" ").toLocaleLowerCase();
    return haystack.includes(text);
  });
  for (const entry of found) list.append(makeRecord(entry));
  $("load-status").textContent = found.length === 0 ? "目前沒有符合條件的公開紀錄。" : "";
}

async function init() {
  try {
    const response = await fetch("./data/index.json", { cache: "no-store" });
    if (!response.ok) throw new Error("HTTP " + response.status);
    const data = await response.json();
    const lookup = new Map((data.verification.cases || []).map(r => [r.id, r]));
    entries = (data.records || []).filter(r => lookup.has(r.id))
      .map(record => ({record, result: lookup.get(record.id)}));
    $("total").textContent = entries.length;
    $("checked").textContent = entries.filter(x => x.result.outcome === "bounded_checks_pass").length;
    $("unchecked").textContent = entries.filter(x => x.result.outcome === "not_checked").length;
    // The initial engine does not implement theorem certification.
    $("certified").textContent = "0";
    $("search").addEventListener("input", update);
    $("outcome").addEventListener("change", update);
    update();
  } catch (error) {
    $("load-status").textContent = "無法讀取本地資料。請先執行 python -m amvo build-site，然後透過本機 HTTP server 啟動；不要直接以 file:// 開啟。";
  }
}
init();
