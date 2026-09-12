// Session-only, per-tab summaries: no URL, title, input values or screenshots retained.
export function updateJourney(previous, context, analysis, domain, now = Date.now()) {
  const valid = previous && now - previous.time < 15 * 60 * 1000;
  const steps = valid ? [...previous.steps] : [];
  const step = {
    signals: [...new Set((analysis.layers || []).flatMap(l => (l.signals || []).map(s => s.id)))].slice(0,20),
    sensitive_field_count: context.sensitive_fields?.length || 0,
    domain_changed: !!valid && previous.domain !== domain,
  };
  if (JSON.stringify(steps.at(-1)) !== JSON.stringify(step)) steps.push(step);
  return {time:now,domain,steps:steps.slice(-8)};
}
