// Only stable evidence changes re-arm a dismissed warning; timestamps do not.
export function warningKey(url, result) {
  const signals = (result?.layers || []).flatMap(layer => (layer.signals || [])
    .filter(s => s.weight > 0).map(s => [s.id, s.weight, s.detail]));
  signals.sort((a, b) => a[0].localeCompare(b[0]));
  return JSON.stringify([url, signals, result?.decision?.risk_score || 0, result?.decision?.display_level, result?.decision?.interrupt_triggers || []]);
}
export function hasWarning(result) {
  return (result?.decision?.risk_score || 0) > 0 ||
    ['banner', 'block'].includes(result?.decision?.display_level);
}

// Include signal details even when talking to an older backend with truncated reasons.
export function warningReasons(result) {
  return [...new Set([
    ...(result?.decision?.reasons || []),
    ...(result?.layers || []).flatMap(layer => (layer.signals || [])
      .filter(signal => signal.weight > 0).map(signal => signal.detail)),
  ].filter(text => typeof text === "string" && text.trim()))];
}

// Keep findings from this visit while asynchronous checks finish independently.
// Acknowledging one card must not acknowledge unrelated findings.
export class WarningCards {
  url = null;
  entries = new Map();
  update(url, result) {
    if (this.url !== url) { this.url = url; this.entries.clear(); }
    for (const text of warningReasons(result)) {
      if (!this.entries.has(text)) this.entries.set(text, { text, dismissed: false });
    }
  }
  dismiss(text) { const entry = this.entries.get(text); if (entry) entry.dismissed = true; }
  dismissAll() { for (const entry of this.entries.values()) entry.dismissed = true; }
  visible(blocking = false) {
    return [...this.entries.values()].filter(entry => blocking || !entry.dismissed);
  }
}
