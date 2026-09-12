// Only stable evidence changes re-arm a dismissed warning; timestamps do not.
export function warningKey(url, result) {
  const signals = (result?.layers || []).flatMap(layer => (layer.signals || [])
    .filter(s => s.weight > 0).map(s => [s.id, s.weight]));
  signals.sort((a, b) => a[0].localeCompare(b[0]));
  return JSON.stringify([url, signals, result?.decision?.risk_score || 0]);
}
export function hasWarning(result) {
  return (result?.decision?.risk_score || 0) > 0 ||
    ['banner', 'block'].includes(result?.decision?.display_level);
}
