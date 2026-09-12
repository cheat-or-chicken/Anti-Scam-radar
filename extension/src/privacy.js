import patterns from '../../script/data/privacy_patterns.json' with {type:'json'};
const rules = patterns.map(({pattern,replacement}) => [new RegExp(pattern,'gi'),replacement]);
export function redactText(text) {
  return rules.reduce((value,[pattern,replacement]) => value.replace(pattern,replacement),text);
}
// Text content only: preserve image bytes and exact navigation URLs required by checks.
export function redactPayload(body) {
  if (!body?.context) return body;
  const context = {...body.context};
  for(const field of ['title','text','html','hidden_text','claimed_brand'])
    if(typeof context[field]==='string') context[field]=redactText(context[field]);
  for(const field of ['scripts','probe_texts','qr_payloads'])
    if(Array.isArray(context[field])) context[field]=context[field].map(item=>typeof item==='string'?redactText(item):item);
  return {...body,context};
}
