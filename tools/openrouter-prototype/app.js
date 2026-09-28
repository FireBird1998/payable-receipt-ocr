const $ = id => document.getElementById(id);
const csrf = document.querySelector('meta[name="prototype-token"]').content;
let lastState = {}, upload = null, renderedCases = false, modelSignature = '', lastRuns = '';
const money = n => n === null || n === undefined ? 'Unknown' : '$' + Number(n).toFixed(6);
const engineName = s => s === 'local-ocr' ? 'Local Tesseract OCR' : s.replace('google/', '');
function node(tag, text, className) { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (className) e.className = className; return e; }
async function post(path, body) {
  const r = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json','X-Prototype-Token':csrf},body:JSON.stringify(body)});
  const data = await r.json(); if (!r.ok) throw new Error(data.error || 'Request failed'); return data;
}
function error(e) { $('error').textContent = e.message || String(e); }
function selectedCases() { return [...document.querySelectorAll('#cases input:checked')].map(i=>i.value); }
function count() { $('case-count').textContent = `${selectedCases().length + (upload ? 1 : 0)} selected`; }
function render(state) {
  lastState = state;
  $('connection').textContent = state.connected ? '● Key connected · local session' : '○ No key connected';
  $('run').disabled = state.busy; $('local').disabled = state.busy; $('stop').disabled = !state.busy;
  $('connect').disabled = state.busy; $('disconnect').disabled = state.busy || !state.connected;
  $('status').textContent = state.progress || 'Ready. No receipt has been sent.';
  if (state.job_error) $('error').textContent = state.job_error;
  const sig = JSON.stringify(state.models);
  if (sig !== modelSignature) {
    modelSignature = sig; $('models').replaceChildren();
    state.models.forEach((m,index)=>{
      const label=node('label',undefined,'choice'), input=node('input'); input.type='checkbox'; input.value=m.id; input.checked=index===0;
      const span=node('span'); span.append(node('b',engineName(m.id)),node('small',`$${(Number(m.pricing.prompt)*1e6).toFixed(2)}/M input · $${(Number(m.pricing.completion)*1e6).toFixed(2)}/M output`));
      label.append(input,span); $('models').append(label);
    });
  }
  if (!renderedCases && state.cases.length) {
    renderedCases=true;
    state.cases.forEach(c=>{
      const label=node('label',undefined,'choice'), input=node('input'); input.type='checkbox';input.value=c.id;input.checked=c.group==='synthetic';input.onchange=count;
      const span=node('span'); span.append(node('b',c.id.split(':').slice(1).join(':')),node('small',`${c.group} · expected ${c.expected_total===null?'abstain':'INR '+c.expected_total}`));
      label.append(input,span);$('cases').append(label);
    }); count();
  }
  const runsSig=JSON.stringify(state.runs);
  if (runsSig === lastRuns) return;
  lastRuns=runsSig;
  $('summary').replaceChildren();
  state.summary.forEach(s=>{
    const card=node('div',undefined,'metric'); card.append(node('b',engineName(s.engine)));
    card.append(node('strong',s.payable_calls?`${s.payable_matches}/${s.payable_calls}`:'—'),node('div','labelled amount matches'));
    card.append(node('div',`${s.negative_matches}/${s.negative_calls} negative controls · ${s.errors} errors`));
    card.append(node('div',`${s.calls} calls / ${s.distinct_images} distinct images`));
    card.append(node('div',`p50 ${(s.p50_ms/1000).toFixed(2)}s · p95 ${(s.p95_ms/1000).toFixed(2)}s`));
    card.append(node('div',s.engine==='local-ocr'?'API fee: none; compute cost unmeasured':`${money(s.cost_usd)} reported · ${s.cost_measured_calls}/${s.calls} costs known`));
    $('summary').append(card);
  });
  $('rows').replaceChildren();
  state.runs.forEach(r=>{
    const tr=node('tr'), label=node('td',r.case_id);label.append(node('small',engineName(r.engine)+` · run ${r.repetition}`));tr.append(label);
    tr.append(node('td',r.labelled?(r.expected_total===null?'Abstain':'₹'+r.expected_total):'Unlabelled'));
    tr.append(node('td',r.ok?(r.total===null?'Abstain':'₹'+r.total):'Error'),node('td',(r.duration_ms/1000).toFixed(2)+'s'));
    tr.append(node('td',r.engine==='local-ocr'?'No API fee':money(r.cost_usd)));
    tr.append(node('td',!r.ok?'Error':r.exact_match===null?'Unscored':r.exact_match?'Match':'Mismatch',r.exact_match===true?'good':'bad'));
    $('rows').append(tr);
  });
  $('detail').textContent=state.runs.length?JSON.stringify(state.runs,null,2):'No observations yet.';
}
async function refresh() { try { const r=await fetch('/api/state'); if(!r.ok) throw new Error('Local server unavailable');render(await r.json()); } catch(e) {error(e);} }
$('connect').onclick=async()=>{const key=$('key').value;$('key').value='';$('error').textContent='';$('connection').textContent='Connecting…';try{await post('/api/connect',{key});await refresh();}catch(e){error(e);$('connection').textContent='Connection failed';}};
$('disconnect').onclick=async()=>{try{await post('/api/disconnect',{});await refresh();}catch(e){error(e);}};
$('synthetic').onclick=()=>{document.querySelectorAll('#cases input').forEach(i=>i.checked=i.value.startsWith('synthetic:'));count();};
$('clear').onclick=()=>{document.querySelectorAll('#cases input').forEach(i=>i.checked=false);count();};
$('upload').onchange=async()=>{const file=$('upload').files[0];if(!file)return;if(file.size>10*1024*1024){error(new Error('Image exceeds 10 MiB'));return;}const reader=new FileReader();reader.onload=()=>{upload=String(reader.result).split(',')[1];$('preview').src=reader.result;$('preview').hidden=false;$('remove-upload').hidden=false;count();};reader.readAsDataURL(file);};
$('remove-upload').onclick=()=>{upload=null;$('upload').value='';$('preview').hidden=true;$('preview').removeAttribute('src');$('remove-upload').hidden=true;count();};
async function run(localOnly) {
  $('error').textContent='';const engines=localOnly?['local-ocr']:[...document.querySelectorAll('#models input:checked')].map(i=>i.value);
  if(!localOnly && $('ocr').checked)engines.push('local-ocr');
  try {await post('/api/run',{case_ids:selectedCases(),engines,upload,consent:$('consent').checked,budget:Number($('budget').value),repetitions:Number($('repetitions').value)});await refresh();}catch(e){error(e);}
}
$('run').onclick=()=>run(false);$('local').onclick=()=>run(true);
$('stop').onclick=async()=>{try{await post('/api/stop',{});$('status').textContent='Stopping after the in-flight call…';}catch(e){error(e);}};
$('download').onclick=async()=>{try{const response=await fetch('/api/report');const report=await response.json();const blob=new Blob([JSON.stringify(report,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=node('a');a.href=url;a.download='receipt-vision-prototype-report.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){error(e);}};
refresh();setInterval(refresh,1500);
