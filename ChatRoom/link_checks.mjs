export function extractLinks(text) {
  const matches=String(text).match(/(?<![\w@/.:])(?:(?:https?:\/\/|www\.)[^\s<>"'\u3000，。！？、；（）]+|(?:[a-z0-9-]+\.)+[a-z]{2,}(?:[/?#][^\s<>"'\u3000，。！？、；（）]*)?)/gi)||[];
  const urls=[];
  for(let raw of matches) {
    raw=raw.replace(/[.,;:!?\])}]+$/g,'');
    try {
      const url=new URL(/^https?:\/\//i.test(raw)?raw:'https://'+raw);
      if(!['http:','https:'].includes(url.protocol)||url.username||url.password||raw.length>8192)continue;
      url.hash='';
      if(!urls.includes(url.href))urls.push(url.href);
    } catch {}
  }
  return urls;
}
export function createLinkChecks(container) {
  let generation=0,active=0,queue=[],seen=new Map();
  async function run(job) {
    active++;
    job.label.textContent='正在讀取網站並分析…';
    try {
      const response=await fetch('/api/check-link',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:job.url}),signal:AbortSignal.timeout(150000)});
      const data=await response.json();
      if(!response.ok)throw Error(data.error||'網址檢查未完成');
      if(job.generation!==generation)return;
      job.card.classList.toggle('warning',data.status==='risk');
      job.label.textContent={risk:'發現風險，先別開啟',not_flagged:'目前未發現警訊，仍需留意',unknown:'無法取得網站內容，尚未確認'}[data.status]||'尚未確認';
      job.details.replaceChildren();
      for(const reason of data.reasons||[]) {const li=document.createElement('li');li.textContent=reason;job.details.append(li);}
      const note=document.createElement('p');note.className='muted';
      note.textContent=`${data.notice} ${data.fetch_status==='unavailable'?'本次未讀取到網頁內容。':''}`;
      job.card.append(note);
      const open=document.createElement('button');open.textContent='了解結果，另開網頁';
      open.onclick=()=>{if(data.status!=='not_flagged'&&!confirm('此網址有風險或尚未完成查證，仍要開啟嗎？'))return;window.open(job.url,'_blank','noopener,noreferrer');};
      job.card.append(open);
    } catch(error) {
      if(job.generation===generation) {
        job.label.textContent='檢查未完成，不代表安全';
        const retry=document.createElement('button');retry.textContent='重試';retry.onclick=()=>{retry.remove();queue.push(job);pump();};
        job.card.append(retry);
      }
    } finally {active--;pump();}
  }
  function pump(){while(active<2&&queue.length)void run(queue.shift());}
  return {
    reset(){generation++;queue=[];seen.clear();container.replaceChildren();},
    scan(text,turn){
      for(const url of extractLinks(text)) {
        if(seen.has(url))continue;
        const card=document.createElement('section');card.className='link-card';
        const title=document.createElement('strong');title.textContent=`第 ${turn} 則 · ${new URL(url).hostname}`;
        const address=document.createElement('div');address.className='muted';address.textContent=url;
        const label=document.createElement('p');label.setAttribute('role','status');label.textContent='已偵測到網址，排隊檢查中…';
        const details=document.createElement('ul');card.append(title,address,label,details);container.append(card);
        seen.set(url,true);queue.push({url,card,label,details,generation});
      }
      pump();
    }
  };
}
