// Real chat UI with deterministic API fixtures; no suspicious sites opened.
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
const browser=await chromium.launch({channel:'chromium',headless:true});
try {
 const page=await browser.newPage();
 let checked=[];
 await page.route('**/api/detector',r=>r.fulfill({json:{configured:true,model:'fixture'}}));
 await page.route('**/api/samples',r=>r.fulfill({json:{samples:[]}}));
 await page.route('**/api/sessions',r=>r.fulfill({json:{session_id:'fixture'}}));
 await page.route('**/api/analyze',async r=>{
  await new Promise(resolve=>setTimeout(resolve,1500));
  await r.fulfill({json:{status:'ok',turn:1,model:'fixture',decision:{status:'monitor',reason:'Fixture',evidence:[],stages:[]},predictions:[]}});
 });
 await page.route('**/api/check-link',async r=>{
  const url=r.request().postDataJSON().url;checked.push(url);
  await new Promise(resolve=>setTimeout(resolve,url.includes('one')?300:50));
  await r.fulfill({json:{status:url.includes('one')?'risk':'unknown',reasons:['測試風險原因'],fetch_status:'unavailable',notice:'未完成不代表安全'}});
 });
 await page.goto('http://127.0.0.1:8000');
 await page.locator('#textFile').setInputFiles({name:'links.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify({messages:[{sender:'counterparty',channel:'chat',text:'https://one.example https://two.example https://one.example'}]}))});
 await page.waitForFunction(()=>!document.getElementById('next').disabled);
 await page.locator('#next').click();
 await page.waitForFunction(()=>document.querySelectorAll('.link-card').length===2);
 assert.equal(await page.locator('.bubble').count(),0,'URL cards appear before slow dialogue analysis finishes');
 await page.waitForFunction(()=>document.querySelector('.link-card.warning'));
 assert.equal(checked.length,2,'duplicate URL checked once');
 assert.equal(await page.locator('.link-card').count(),2,'independent results do not overwrite');
 assert.ok((await page.locator('#linkChecks').innerText()).includes('尚未確認'));
 await page.waitForFunction(()=>!document.getElementById('reset').disabled);
 await page.locator('#reset').click();
 await page.waitForFunction(()=>document.querySelectorAll('.link-card').length===0);
 await page.route('**/api/analyze',async r=>{
  const turn=r.request().postDataJSON().message.turn;
  await r.fulfill({json:{status:'ok',turn,model:'fixture',decision:{status:'warn',reason:'領獎索取卡片資料',recommended_action:'先不要送出',evidence:[],stages:[]},predictions:[],intervention:{phase:turn===1?'request_or_risk':'reported_submitted'}}});
 });
 await page.locator('#textFile').setInputFiles({name:'warning.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify({messages:[{sender:'page',text:'請填卡號領獎'},{sender:'user',text:'卡號送出了'}]}))});
 await page.waitForFunction(()=>!document.getElementById('auto').disabled);
 await page.locator('#auto').click();
 await page.waitForFunction(()=>document.getElementById('status').textContent.includes('已暫停重播'));
 assert.equal(await page.locator('.bubble').count(),1,'warning pauses before playing the submission');
 assert.ok((await page.locator('#next').innerText()).includes('剩 1 則'));
 await page.locator('#next').click();
 await page.waitForFunction(()=>document.getElementById('verdict').textContent.includes('你表示已送出資料'));
 assert.equal(await page.locator('.bubble').count(),2,'manual continuation still works');
 console.log('PASS: warning pauses replay; reported submission wording; manual continuation');
 console.log('PASS: immediate URL detection; asynchronous independent cards; deduplication; risk + unknown; reset');
} finally {await browser.close();}
