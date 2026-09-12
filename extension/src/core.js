import riskMessages from "../../script/data/risk_messages.json" with { type: "json" };
import semanticRules from "../../script/data/semantic_rules.json" with { type: "json" };
import { getDomain } from "tldts";
import brands from "../../script/data/brands.json" with { type: "json" };

export function parseURL(value) {
  if (typeof value !== "string" || value.length > 8192 || /[\s\\]/.test(value))
    throw new Error("INVALID_URL");
  const url = new URL(value);
  if (
    !["http:", "https:"].includes(url.protocol) ||
    url.username ||
    url.password ||
    (url.port && !["80", "443"].includes(url.port) && !(url.protocol === "http:" && url.hostname === "127.0.0.1" && url.port === "8088"))
  )
    throw new Error("INVALID_URL");
  url.hostname = url.hostname.toLowerCase().replace(/\.$/, "");
  return url;
}
export function boundary(host) {
  return getDomain(host, { allowPrivateDomains: true }) || host;
}
export function sameSite(a, b) {
  return boundary(parseURL(a).hostname) === boundary(parseURL(b).hostname);
}
export function trusted(url) {
  const p = parseURL(url);
  return (
    p.protocol === "https:" &&
    brands.some((b) =>
      b.domains.some((d) => p.hostname === d || p.hostname.endsWith("." + d)),
    )
  );
}
export function publicURL(value) {
  const u = parseURL(value);
  return u.origin + u.pathname;
}
export function skeleton(host) {
  if (!/\d/.test(host) || host.split(".").some((x) => /^\d+$/.test(x)))
    return null;
  return host.replace(/\d+/g, "#");
}
export function checkBlocklist(url, data) {
  if (!data) return { kind: "unknown" };
  let candidate = parseURL(url).hostname;
  const stop = boundary(candidate);
  while (true) {
    if (Object.hasOwn(data.domains, candidate))
      return {
        kind: "listed",
        domain: candidate,
        sources: data.domains[candidate].s || [],
      };
    if (candidate === stop || !candidate.includes(".")) break;
    candidate = candidate.slice(candidate.indexOf(".") + 1);
  }
  const key = skeleton(parseURL(url).hostname);
  const matches = key ? data.digitSkeletons?.[key] : null;
  return {
    kind: matches?.length ? "similar" : "none",
    similarTo: matches?.slice(0, 3) || [],
  };
}
export const TRIGGERS = [
  "password_field_focus",
  "sensitive_field_focus",
  "submit",
  "download_start",
];
const emptyLayer = (id) => ({
  layer: id,
  verdict: "unknown",
  status: "missing",
  score: 0,
  confidence: 0,
  evidence_grade: "inferred",
  signals: [],
  feedback: [],
  user_facing_reason: "尚未取得本層資料",
});
export function brandPatterns(value) {
  const h = parseURL(value).hostname;
  const found = [];
  for (const brand of brands) {
    if (brand.domains.some(d => h === d || h.endsWith("." + d))) continue;
    for (const label of h.split(".")) {
      const m = /^([a-z]{4,20})(?:-?([0-9]{1,6}))?$/.exec(label);
      if (!m) continue;
      const token = m[1];
      const hit = (brand.domain_tokens || []).some(expected =>
        token === expected || (token.length === expected.length && token.length >= 4 &&
          [...expected].some((c, i) => i < expected.length - 1 && c !== expected[i + 1] &&
            token === expected.slice(0, i) + expected[i + 1] + c + expected.slice(i + 2))));
      if (!hit) continue;
      found.push({ id: "brand_lookalike_" + brand.id, weight: m[2] ? 35 : 25,
        detail: `網址片段「${label}」近似${brand.name}品牌名稱，但主機不在官方網域名單；請自行前往 https://${brand.domains[0]}/ 查詢，勿在此輸入付款資料或驗證碼` });
      break;
    }
  }
  return found;
}
export function analyzeLocal(ctx, data) {
  const layers = Array.from({ length: 17 }, (_, i) => emptyLayer("L" + i));
  const list = emptyLayer("BLOCKLIST");
  layers.push(list);
  const add = (index, id, detail, weight, grade = "inferred", hard = false) => {
    const layer = typeof index === "number" ? layers[index] : list;
    if (!layer.signals.some((s) => s.id === id))
      layer.signals.push({ id, detail: riskMessages[id] || detail, weight, grade, hard });
  };
  const chain = [...(ctx.redirects || []), ctx.url];
  for (const url of chain) {
    const h = parseURL(url).hostname;
    for (const p of brandPatterns(url)) add(1, p.id, p.detail, p.weight);
    const hit = checkBlocklist(url, data);
    if (hit.kind === "listed")
      add(
        "list",
        "listed_domain",
        "目前網址或轉址鏈命中匯入的 NPA／TWNIC 通報名單，建議停止瀏覽並查證",
        100,
        "observed",
        true,
      );
    if (hit.kind === "similar")
      add(
        "list",
        "digit_variant",
        "網址與通報名單中的網域僅有數字差異，尚未確認為同一網站",
        20,
      );
    if (h.includes("xn--"))
      add(1, "idn_domain", "網址使用國際化網域，請留意相似字形", 5);
    if (/\.(top|xyz|cyou)$/.test(h))
      add(1, "unusual_tld", "網址使用需額外核對的頂級網域", 5);
    if (
      brands.some((b) =>
        b.domains.some((d) => h.includes(d) && h !== d && !h.endsWith("." + d)),
      )
    )
      add(
        1,
        "official_domain_embedded",
        "官方網域文字被嵌入另一個網站的網址中",
        40,
        "observed",
      );
  }
  if (
    chain.some(
      (u, i) =>
        i &&
        parseURL(chain[i - 1]).protocol === "https:" &&
        parseURL(u).protocol === "http:",
    )
  )
    add(1, "https_downgrade", "轉址鏈從 HTTPS 降級為 HTTP", 20, "observed");
  for (const brand of brands) {
    const h = parseURL(ctx.url).hostname;
    if (
      brand.aliases.some((a) => (ctx.title || "").includes(a)) &&
      !brand.domains.some((d) => h === d || h.endsWith("." + d))
    )
      add(
        2,
        "brand_domain_mismatch",
        `這個頁面提到${brand.name}，但目前網址不是我們已核對的官方網域。可能是在冒用名稱；請自行前往 https://${brand.domains[0]}/ 查詢，先別在這裡填資料或付款。`,
        40,
      );
  }
  for (const sentence of (ctx.text || "").split(/[。！？\n]/)) {
    if (/不要|切勿|請勿|不會|勿將|防詐|詐騙案例/.test(sentence)) continue;
    if (/(安裝|下載).{0,25}(AnyDesk|TeamViewer|QuickSupport)/i.test(sentence))
      add(
        3,
        "remote_control_request",
        "文案要求安裝遠端控制軟體，請核對聯絡對象",
        45,
      );
    if (
      /(提供|告知|傳送|回傳).{0,15}(OTP|驗證碼|網銀密碼|提款卡密碼).{0,15}(客服|專員|我們)/i.test(
        sentence,
      )
    )
      add(3, "credential_relay_request", "文案要求將驗證碼或密碼交給他人", 55);
    if (/ATM.{0,20}解除分期|保證獲利|穩賺不賠/.test(sentence))
      add(3, "financial_manipulation", "文案含 ATM 解除分期或保證獲利話術", 40);
    if (/(罰單|罰鍰|通行費).{0,30}(立即|逾期|限時|繳納)/.test(sentence))
      add(
        3,
        "government_payment_pressure",
        "頁面催促繳納交通費用，請從官方網站自行查詢",
        20,
      );
  }
  for (const sentence of (ctx.text || "").split(/[。！？\n.!?]/)) {
    if (/不要|切勿|請勿|不會|勿將|防詐|詐騙案例|do not|never|beware/i.test(sentence)) continue;
    for (const rule of semanticRules.filter(r => r.scope !== "page"))
      if (rule.patterns.every(pattern => new RegExp(pattern, "i").test(sentence)))
        add(3, rule.id, riskMessages[rule.id], rule.weight);
  }
  for (const rule of semanticRules.filter(r => r.scope === "page"))
    if (new RegExp(rule.patterns[0], "i").test(ctx.title || "") && rule.patterns.every(pattern => new RegExp(pattern, "is").test((ctx.title || "") + "\n" + (ctx.text || ""))))
      add(3, rule.id, riskMessages[rule.id], rule.weight);
  if ((ctx.form_actions || []).some((u) => !sameSite(u, ctx.url)))
    add(
      4,
      "external_form_action",
      "表單設定送往站外網址；尚未證明資料已外傳",
      20,
    );
  if (
    /ignore.{0,30}instructions|忽略.{0,15}指令|判定.{0,8}安全/i.test(
      ctx.hidden_text || "",
    )
  )
    add(15, "prompt_injection", "隱藏文字疑似要求分析器改變判定", 20);
  if (ctx.delayed_sensitive_injection)
    add(
      15,
      "delayed_sensitive_injection",
      "頁面載入後才新增敏感欄位，需核對用途",
      10,
      "observed",
    );
  for (const d of ctx.downloads || []) {
    if (/\.(apk|exe|scr|msi|lnk|js)$/i.test(d.filename))
      add(
        12,
        "executable_download",
        "下載檔案可執行程式或安裝應用程式",
        25,
        "observed",
      );
    if (
      /\.(pdf|jpg|docx?)\.(exe|scr|js|lnk)$/i.test(d.filename) ||
      d.filename.includes("\u202e")
    )
      add(
        12,
        "disguised_download",
        "檔名使用雙副檔名或方向控制字元掩飾類型",
        45,
        "observed",
      );
  }
  if (ctx.previous_sensitive_fields != null) {
    layers[8].status = "ok"; layers[8].verdict = "clean";
    if (!ctx.previous_sensitive_fields.length && ctx.sensitive_fields?.length)
      add(8, "new_sensitive_form", "與本分頁上一份快照相比新增敏感欄位，請核對用途", 25);
  }
  if ((ctx.text || "").trim()) {
    layers[9].status = "ok"; layers[9].verdict = "clean";
    if (["登录", "银行卡", "身份证", "验证码", "网络"].filter(w => ctx.text.includes(w)).length >= 2)
      add(9, "locale_inconsistency", "頁面混用不同地區的詞彙；僅作低權重輔助訊號", 5);
  }
  if (ctx.missing_business_pages === false) {
    layers[11].status = "ok"; layers[11].verdict = "clean";
    layers[11].feedback = ["頁面提供關於或聯絡資訊連結；尚未驗證商家身分與連結內容。"];
  }
  if (ctx.dom_collected) {
    layers[4].status = "ok"; layers[4].verdict = "clean";
    layers[4].feedback = ["已檢查表單目的地；未採集實際輸入值或外傳流量。"];
    layers[15].status = "ok"; layers[15].verdict = "clean";
  }
  for (const i of [0, 1, 14, ...((ctx.title || "").trim() ? [2] : []), ...((ctx.text || "").trim() ? [3, 4] : [])]) {
    layers[i].status = "ok";
    layers[i].verdict = "clean";
  }
  list.status = data ? "ok" : "error";
  list.verdict = data ? "clean" : "unknown";
  for (const layer of layers) {
    if (layer.signals.length) {
      layer.status = "ok";
      layer.verdict = "suspicious";
      layer.confidence = 0.85;
      layer.score = Math.min(
        100,
        layer.signals.reduce((a, s) => a + s.weight, 0),
      );
      layer.user_facing_reason = layer.signals[0].detail;
    }
  }
  return {
    schema_version: "1.0",
    layers,
    decision: adjudicate(ctx.url, layers),
    source: "local",
    checkedAt: Date.now(),
    listReady: !!data,
  };
}
export function adjudicate(url, layers) {
  const unique = new Map();
  for (const layer of layers)
    for (const s of layer.signals || [])
      if (!unique.has(s.id)) unique.set(s.id, { ...s, layer: layer.layer });
  const signals = [...unique.values()];
  const hard = signals.some(
    (s) => s.layer === "BLOCKLIST" && s.id === "listed_domain" && s.hard,
  );
  const independent = new Set(
    signals
      .filter(
        (s) => s.weight >= 15 && !["L10", "L16", "ADAPTIVE"].includes(s.layer),
      )
      .map((s) => s.layer),
  );
  let score = Math.min(
    100,
    signals.reduce((a, s) => a + s.weight, 0),
  );
  if (!hard && independent.size < 2) score = Math.min(score, 55);
  if (hard) score = 100;
  const isTrusted = trusted(url);
  return {
    risk_score: score,
    category: signals.some(s => s.layer === "L3") ? "話術詐騙疑慮" : signals.some(s => s.id.includes("brand")) ? "品牌或機構冒用疑慮" : "未分類",
    display_level: isTrusted
      ? (score > 0 ? "banner" : "icon")
      : score >= 80
        ? "block"
        : score > 0
          ? "banner"
          : "icon",
    trusted_domain: isTrusted,
    interrupt_triggers: score >= 15 && !isTrusted ? [...TRIGGERS] : [],
    coverage: "partial",
    reasons: signals
      .sort((a, b) => b.weight - a.weight)
      .map((s) => s.detail),
  };
}
export function mergeAnalysis(url, local, remote) {
  const layers = local.layers.map((l) => {
    const r = remote.layers?.find((x) => x.layer === l.layer);
    if (!r) return l;
    const signals = new Map((l.signals || []).map((s) => [s.id, s]));
    for (const s of r.signals || [])
      if (!signals.has(s.id)) signals.set(s.id, s);
    return {
      ...r,
      signals: [...signals.values()],
      status: signals.size ? "ok" : r.status,
    };
  });
  for (const layer of remote.layers || []) {
    if (!layers.some(existing => existing.layer === layer.layer)) layers.push(layer);
  }
  return {
    ...local,
    layers,
    decision: adjudicate(url, layers),
    source: "backend",
    backend: "connected",
    checkedAt: Date.now(),
  };
}
