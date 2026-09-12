import test from 'node:test';
import assert from 'node:assert/strict';
import { warningKey, hasWarning } from '../src/warning_state.js';
import { analyzeLocal } from '../src/core.js';
test('dismissal fingerprint ignores timestamps but changes with page or evidence', () => {
  const a = analyzeLocal({url:'https://example.com',text:'登录 银行卡'},null);
  assert.ok(hasWarning(a));
  assert.equal(a.decision.display_level,'banner');
  assert.equal(warningKey('/a',a),warningKey('/a',{...a,checkedAt:0}));
  assert.notEqual(warningKey('/a',a),warningKey('/b',a));
  const b=analyzeLocal({url:'https://example.com',text:'登录 银行卡。請下載 AnyDesk。'},null);
  assert.notEqual(warningKey('/a',a),warningKey('/a',b));
});
test('shared social engineering categories and education negative control', () => {
  for (const [text,id] of [['您的裝置感染病毒，請立即下載修復工具。','scareware_pressure'],
    ['完成真人驗證，按 Win+R 再貼上指令。','fake_verification_command'],
    ['要提領資金，請先支付保證金。','advance_fee_request']]) {
    const r=analyzeLocal({url:'https://example.com',text},null);
    assert.equal(r.decision.category,'話術詐騙疑慮');
    assert.ok(r.layers[3].signals.some(s=>s.id===id));
  }
  assert.equal(analyzeLocal({url:'https://example.com',text:'防詐提醒：不要先支付保證金才能提領。'},null).decision.risk_score,0);
});

test('trading promotion requires platform title plus growth and reliability claims', () => {
  for (const [title,text] of [['AI-powered trading platform','98% Reliability 10x Growth potential'],
    ['KI-gestützte Handelsplattform','98% Verlässlichkeit 10x Wachstumspotenzial'],
    ['人工智能交易平台','98% 可靠性 10倍 增长潜力']]) {
    const r=analyzeLocal({url:'https://example.com',title,text},null);
    assert.equal(r.decision.display_level,'banner');
    assert.ok(r.layers[3].signals.some(s=>s.id==='unsubstantiated_trading_claims'));
  }
  const r=analyzeLocal({url:'https://example.com',title:'News report',text:'trading platform claims 98% Reliability 10x Growth potential'},null);
  assert.equal(r.decision.risk_score,0);
});

test('all problems remain in the decision and older truncated results show every signal', async () => {
  const { warningReasons } = await import('../src/warning_state.js');
  const result = analyzeLocal({url:'https://fake.example', title:'監理服務網',
    text:'銀行卡 登录 請下載 AnyDesk。您的裝置感染病毒，請立即下載修復工具。要提領資金，請先支付保證金。'}, null);
  const signals = result.layers.flatMap(l => l.signals).filter(s => s.weight > 0);
  assert.ok(signals.length > 3);
  assert.equal(result.decision.reasons.length, signals.length);
  result.decision.reasons = result.decision.reasons.slice(0, 1);
  for (const signal of signals) assert.ok(warningReasons(result).includes(signal.detail));
  assert.equal(warningReasons(result).length, new Set(signals.map(s => s.detail)).size);
});

test('escalating to block or adding an interrupt re-arms the same score', () => {
  const a = {decision:{risk_score:20,display_level:'banner',interrupt_triggers:[]}};
  assert.notEqual(warningKey('/a', a), warningKey('/a', {...a, decision:{...a.decision, display_level:'block'}}));
  assert.notEqual(warningKey('/a', a), warningKey('/a', {...a, decision:{...a.decision, interrupt_triggers:['submit']}}));
});

test('independent cards survive partial results, dismiss separately and reset on navigation', async () => {
  const {WarningCards} = await import('../src/warning_state.js');
  const cards = new WarningCards();
  const result = reasons => ({decision:{reasons}});
  cards.update('/a', result(['冒用政府', '要求付款']));
  cards.dismiss('冒用政府');
  cards.update('/a', result(['要求付款', '要求驗證碼']));
  assert.deepEqual(cards.visible().map(e => e.text), ['要求付款', '要求驗證碼']);
  cards.update('/a', result(['冒用政府']));
  assert.deepEqual(cards.visible().map(e => e.text), ['要求付款', '要求驗證碼']);
  assert.equal(cards.visible(true).length, 3);
  cards.update('/b', result(['其他頁面']));
  assert.deepEqual(cards.visible().map(e => e.text), ['其他頁面']);
});
