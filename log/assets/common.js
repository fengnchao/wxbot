const $ = s => document.querySelector(s);
const esc = s => (s==null?'':String(s)).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const p2 = n => String(n).padStart(2,'0');
const d2 = t => { const d=new Date(t*1000); return `${d.getFullYear()}-${p2(d.getMonth()+1)}-${p2(d.getDate())}`; };
const hm = t => { const d=new Date(t*1000); return `${p2(d.getHours())}:${p2(d.getMinutes())}`; };
const full = t => { if(!t) return '-'; const d=new Date(t*1000);
  return `${d.getFullYear()}-${p2(d.getMonth()+1)}-${p2(d.getDate())} ${p2(d.getHours())}:${p2(d.getMinutes())}:${p2(d.getSeconds())}`; };
const ago = t => { if(!t) return '-'; const s=(Date.now()/1000)-t;
  if(s<60) return '刚刚'; if(s<3600) return Math.floor(s/60)+'分钟前';
  if(s<86400) return Math.floor(s/3600)+'小时前'; return Math.floor(s/86400)+'天前'; };

let state = { tab:'workflow', jobUid:'all', jobShowDone:false, jobs:null,jRequest:0,jobDeleting:'',jobError:'',jobMessage:'',gRequest:0, auto:0, timer:null,
              wdata:null, wUid:'all', wOrder:'desc', wKind:'flow',wRequest:0,wFlowOffset:0,
              gdata:null, gUid:'all', gOpen:{}, gError:'',
              gNewsDraft:null,gNewsVersion:'',gNewsBusy:false,gNewsMessage:'',gNewsError:'',
              hdata:null, hstatus:null, hStatusError:'', hContact:'', hSkills:[], hSkillsContact:'', hRequest:0, hDraft:null, hError:'', hSaved:'',
              hTriggering:false, hTriggerMessage:'',hDrafts:new Map(),
              qdata:null,qContact:'',qState:'all',qScope:'all',qOffsets:{inbox:0,batches:0,outbox:0,rounds:0,telegram:0},qOffset:0,qRequest:0,qError:'',qBusy:false,qMessage:'',qActionFailed:false,
              cdata:null,cSection:'basic',cSearch:'',cRequest:0,cError:'',viewSearch:{},
              cDrafts:new Map(),cMessages:new Map(),cBusy:new Set(),cRefreshNeeded:false };

async function get(u){
  const r = await fetch(u); if(!r.ok)throw new Error('读取失败（HTTP '+r.status+'）');
  const data=await r.json(); markRefreshed();return data;
}

function markRefreshed(){const node=$('#refresh-status');if(node)node.textContent='最近读取 '+new Date().toLocaleTimeString('zh-CN',{hour12:false});}
function currentQuery(){return (state.viewSearch[state.tab]||'').trim().toLowerCase();}
function matchesQuery(...values){const q=currentQuery();return !q||values.some(v=>String(v??'').toLowerCase().includes(q));}
function longText(text,limit=100,key=''){
  const value=String(text??'');return value.length<=limit?esc(value):`<details class="long-text" ${key?`data-detail="${esc(key)}"`:''}><summary>${esc(value.slice(0,limit))}…</summary><div class="pre">${esc(value)}</div></details>`;
}
const panePositions=new Map(),detailStates=new Map();
function rememberPane(){
  const pane=$('#pane');if(!pane||pane.dataset.view!==state.tab)return;
  panePositions.set(state.tab,{top:pane.scrollTop||0,list:$('#list').scrollTop||0});
  pane.querySelectorAll('details[data-detail]').forEach(el=>detailStates.set(state.tab+':'+el.dataset.detail,el.open));
}
function restorePane(){
  const pane=$('#pane');pane.dataset.view=state.tab;
  pane.querySelectorAll('details').forEach((el,i)=>{
    if(!el.dataset.detail)el.dataset.detail='section:'+i+':'+(el.querySelector('summary')?.textContent||'').slice(0,90);
    const key=state.tab+':'+el.dataset.detail;
    if(detailStates.has(key))el.open=detailStates.get(key);
    el.ontoggle=()=>detailStates.set(key,el.open);
  });
  const position=panePositions.get(state.tab);
  if(position){pane.scrollTop=position.top;$('#list').scrollTop=position.list;}
}
function preservingPane(render){return function(...args){
  rememberPane();
  const active=typeof document.activeElement==='object'?document.activeElement:null;
  const focus=active&&$('#pane').contains?.(active)?{id:active.id,key:active.getAttribute('data-focus-key'),label:active.getAttribute('aria-label'),start:active.selectionStart,end:active.selectionEnd}:null;
  const result=render.apply(this,args);restorePane();
  if(focus){const node=focus.key?Array.from($('#pane').querySelectorAll('[data-focus-key]')).find(el=>el.getAttribute('data-focus-key')===focus.key):focus.id?document.getElementById(focus.id):Array.from($('#pane').querySelectorAll('[aria-label]')).find(el=>el.getAttribute('aria-label')===focus.label);
    if(node){node.focus({preventScroll:true});try{node.setSelectionRange(focus.start,focus.end);}catch{}}}
  return result;
};}
function expandPage(open){
  $('#pane').querySelectorAll('details').forEach(el=>{el.open=open;if(el.dataset.detail)detailStates.set(state.tab+':'+el.dataset.detail,open);});
  if(state.tab==='groups'&&state.gdata){state.gdata.message_types.forEach(t=>state.gOpen[t.type]=open);renderGroupsPane();}
}
// Only display preferences belong in browser storage. Drafts and business data stay in memory.
function readPreference(name,fallback){try{return JSON.parse(localStorage.getItem('butler.ui.'+name))??fallback;}catch{return fallback;}}
function savePreference(name,value){if(!['order','listCollapsed'].includes(name))return;try{localStorage.setItem('butler.ui.'+name,JSON.stringify(value));}catch{}}
