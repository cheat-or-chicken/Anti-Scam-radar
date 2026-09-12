const $ = id => document.getElementById(id);
const stageNames={S0:'接觸',S1:'建立理由',S2:'施加壓力',S3:'可信表象',S4:'管道／權限轉移',S5:'付款／敏感權限',S6:'拖延／追加要求'};
let queue=[], index=0, participants={}, session=null, turn=0, channel=null, busy=false, playing=false;
let mode='json', title='', original=null, results=[];
async function api(path, body) {
  const response=await fetch(path, body===undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const value=await response.json();
  if(!response.ok) throw new Error(value.error || '服務無法連線');
  return value;
}
function state() {
  $('next').disabled=busy || !session || index>=queue.length;
  $('auto').disabled=busy && !playing || !session || index>=queue.length;
  $('reset').disabled=busy || !original;
  $('loadSample').disabled=busy; $('textFile').disabled=busy; $('sample').disabled=busy;
  $('messageInput').disabled=mode!=='txt'||!session||busy;
  $('send').disabled=$('messageInput').disabled;
  $('export').disabled=!results.length;
  $('next').textContent=`下一則（剩 ${queue.length-index} 則）`;
  $('auto').textContent=playing?'暫停重播':'自動重播';
}
async function load(data, name, type='json') {
  if(busy) return;
  if(type==='json' && (!Array.isArray(data.messages)||!data.messages.length||data.messages.length>300)) throw new Error('JSON 必須包含1至300則 messages');
  const incoming=type==='json'?data.messages:data;
  if(!incoming.length || incoming.some(m=>typeof m.text!=='string'||!m.text.trim())) throw new Error('每則訊息都必須有 text');
  playing=false; busy=true; state();
  try {
    const created=await api('/api/sessions',{});
    queue=incoming; participants=type==='json'?(data.participants||{}):{counterparty:name,user:'我'};
    session=created.session_id; index=0; turn=0; channel=null; results=[]; mode=type; title=name;
    original={data,name,type}; $('chatTitle').textContent=name; $('messages').replaceChildren();
    $('trace').replaceChildren(); $('evidence').replaceChildren(); $('stages').replaceChildren();
    $('predictions').textContent='等待有依據的預測'; $('verdict').textContent='等待對話';
    $('reason').textContent='已建立新的分析工作階段'; $('advice').textContent='';
    $('firstAlert').textContent='尚無示警'; $('decisionCard').classList.remove('warning');
    $('status').textContent=`已載入 ${queue.length} 則；只將播放到的訊息送出分析`;
  } finally {busy=false; state();}
}
function append(message) {
  const area=$('messages');
  if(message.channel!==channel) {
    const divider=document.createElement('div');divider.className='divider';
    divider.textContent=`── ${message.channel || '對話'} ──`;area.append(divider); channel=message.channel;
  }
  const bubble=document.createElement('div');bubble.className='bubble'+(message.sender==='user'?' mine':'');
  const speaker=document.createElement('span');speaker.className='speaker';
  speaker.textContent=`#${message.turn} · ${participants[message.sender] || message.sender}`;
  bubble.append(speaker,document.createTextNode(message.text));
  for(const attachment of message.attachments||[]) {
    if(!attachment.caption)continue;
    const caption=document.createElement('div');caption.className='attachment';caption.textContent=attachment.caption;bubble.append(caption);
  }
  area.append(bubble);area.scrollTop=area.scrollHeight;
}
function render(result) {
  const decision=result.decision;
  $('decisionCard').classList.toggle('warning',decision?.status==='warn');
  $('evidence').replaceChildren();$('stages').replaceChildren();$('advice').textContent='';
  const label={insufficient:'尚無具體風險依據',monitor:'持續觀察，未示警',warn:'請暫停操作，出現可疑要求'};
  if(!decision) { $('verdict').textContent='分析失敗';$('reason').textContent=result.error; }
  else {
    $('verdict').textContent=label[decision.status];$('reason').textContent=decision.reason;
    if(decision.status==='warn')$('advice').textContent=decision.recommended_action;
    for(const e of decision.evidence) {
      const q=document.createElement('blockquote');q.textContent=`第 ${e.turn} 則：「${e.quote}」`;$('evidence').append(q);
    }
    for(const stage of decision.stages) {const b=document.createElement('span');b.className='badge';b.textContent=`${stage} ${stageNames[stage]||''}`;$('stages').append(b);}
  }
  const firstWarning=results.find(r=>r.result.decision?.status==='warn');
  $('firstAlert').textContent=firstWarning?`歷史警報保留｜首次第 ${firstWarning.result.turn} 則：${firstWarning.result.decision.reason}`:'尚無示警';
  $('predictions').replaceChildren();
  if(!(result.predictions||[]).length)$('predictions').textContent='目前沒有足夠依據提出下一步預測。';
  for(const p of result.predictions||[]) {
    const row=document.createElement('div');row.className='prediction';
    const labels={matched:`已命中（第${p.matched_turn}則）`,missed:'視窗內未命中',pending:index===queue.length&&mode==='json'?'對話已結束，尚未確認':'待觀察'};
    row.textContent=`第${p.created_turn}則預測：${p.action} · ${labels[p.status]}`;$('predictions').append(row);
  }
  const row=document.createElement('div');row.className='trace-row';
  row.textContent=`#${result.turn} · ${decision?label[decision.status]:'分析失敗'} · ${result.elapsed_seconds}s`;
  $('trace').prepend(row);
}
async function advance(raw) {
  busy=true;state();$('status').textContent='正在分析本輪…';
  try {
    const message={...raw,turn:turn+1};
    const result=await api('/api/analyze',{session_id:session,message});
    turn++; if(raw===queue[index])index++;
    append(message);results.push({message,result});render(result);
    $('status').textContent=`已播放 ${turn} 則 · ${result.model}`;
    if(result.status==='analysis_error'){playing=false;$('status').textContent=result.error;}
  } catch(error) {playing=false;$('status').textContent=error.message;}
  finally {busy=false;state();}
}
$('next').onclick=()=>{if(!busy&&index<queue.length)advance(queue[index]);};
$('auto').onclick=async()=>{
  if(playing){playing=false;state();return;}
  playing=true;state();
  while(playing&&index<queue.length){await advance(queue[index]);}
  playing=false;state();
};
$('reset').onclick=()=>load(original.data,original.name,original.type).catch(e=>$('status').textContent=e.message);
$('loadSample').onclick=async()=>{try{const name=$('sample').value;if(name)await load(await api('/api/sample?name='+encodeURIComponent(name)),name);}catch(e){$('status').textContent=e.message;}};
$('textFile').onchange=async()=>{
  try {const file=$('textFile').files[0];if(!file)return;const content=await file.text();
    if(file.name.endsWith('.json'))await load(JSON.parse(content),file.name);
    else await load(content.split(/\r?\n/).map(s=>s.trim()).filter(Boolean).map(text=>({text,sender:'counterparty',channel:'chat'})),file.name,'txt');
  }catch(e){$('status').textContent=e.message;}
};
$('sendForm').onsubmit=async e=>{e.preventDefault();const text=$('messageInput').value.trim();if(text&&!busy){await advance({text,sender:'user',channel:'chat'});$('messageInput').value='';}};
$('export').onclick=()=>{
  const blob=new Blob([JSON.stringify({title,session_id:session,results},null,2)],{type:'application/json'});
  const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='dialogue-analysis.json';a.click();URL.revokeObjectURL(url);
};
Promise.all([api('/api/detector'),api('/api/samples')]).then(([config,data])=>{
  $('connection').textContent=config.configured?`模型：${config.model} · API已設定`:'尚未設定 OPENAI_API_KEY';
  for(const name of data.samples){const option=document.createElement('option');option.value=name;option.textContent=name.replace('.replay.json','');$('sample').append(option);}
}).catch(e=>$('connection').textContent=e.message);
