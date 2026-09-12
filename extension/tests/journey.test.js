import test from 'node:test';
import assert from 'node:assert/strict';
import {updateJourney} from '../src/journey.js';
import {analyzeLocal,mergeAnalysis} from '../src/core.js';
test('journey deduplicates, expires, bounds steps and omits page contents',()=>{
 const ctx={text:'secret',url:'https://example.com/?token=secret',sensitive_fields:['otp']};
 const analysis={layers:[{signals:[{id:'otp_request'}]}]};
 const first=updateJourney(null,ctx,analysis,'a',0);
 assert.equal(updateJourney(first,ctx,analysis,'a',1).steps.length,1);
 assert.equal(updateJourney(first,ctx,analysis,'b',1).steps[1].domain_changed,true);
 assert.equal(updateJourney(first,ctx,analysis,'b',900001).steps.length,1);
 assert.ok(!JSON.stringify(first).includes('secret'));
 let history=first;
 for(let i=1;i<15;i++) history=updateJourney(history,ctx,analysis,String(i),i);
 assert.ok(history.steps.length<=8);
});
test('accepted contextual warning survives zero-score merge without becoming a block',()=>{
 const local=analyzeLocal({url:'https://example.com'},null);
 const result=mergeAnalysis('https://example.com',local,{layers:[],workflow:{status:'ok',accepted_action:'warn'},decision:{reasons:['AI 綜合判斷']}});
 assert.equal(result.decision.display_level,'banner');
 assert.equal(result.decision.risk_score,0);
 assert.ok(result.decision.reasons.includes('AI 綜合判斷'));
});
