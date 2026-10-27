function workflowReady(){
  return typeof renderWorkflow==='function'&&typeof startWorkflow==='function'&&
    typeof stopWorkflow==='function'&&typeof loadWorkflow==='function';
}
function renderWorkflowUnavailable(){
  $('#list').innerHTML='';
  $('#pane').innerHTML='<div class="head" role="status"><h2>工作流模块未加载</h2><p>请先手动重启 log 服务，再刷新此页面。</p><p class="monitor-note">更新文件后，仍在运行的旧 log 进程可能无法提供新增的 workflow.js、workflow.css 和工作流接口。若重启后仍有提示，请检查浏览器网络面板中的脚本加载错误。</p><p class="monitor-note">左侧其他管理页面仍可使用；Butler、wxbot 无需重启。</p></div>';
}
function switchTab(t){
  rememberPane();
  if(typeof stopWorkflow==='function')stopWorkflow();
  state.tab = t;
  document.body.classList.toggle('workflow-page',t==='workflow');
  $('#pane').dataset.view='';
  const titles={workflow:'实时工作流',wxbot:'消息流转',queue:'收发队列',runtime:'模型与记忆',users:'用户与记忆',heartbeat:'角色与心跳',jobs:'定时任务',groups:'用户分组',configuration:'配置管理','telegram-relay':'Telegram 转发'};
  $('#page-title').textContent=titles[t];
  $('#view-search').value=state.viewSearch[t]||'';
  $('#view-search').placeholder=t==='workflow'?'搜索用户 / UID / 消息 ID':t==='wxbot'?'筛选本页消息':t==='queue'?'筛选本页任务':t==='heartbeat'?'搜索 Skill 或执行记录':'搜索当前记录';
  $('#view-search').classList.toggle('hide',t==='configuration'||t==='telegram-relay');
  $('#tab-wxbot').classList.toggle('on', t==='wxbot');
  $('#tab-workflow').classList.toggle('on', t==='workflow');
  $('#b-auto').classList.toggle('hide',t==='workflow');
  $('#b-contacts').classList.toggle('hide',t==='workflow');
  $('#tab-jobs').classList.toggle('on', t==='jobs');
  $('#tab-groups').classList.toggle('on', t==='groups');
  $('#tab-heartbeat').classList.toggle('on', t==='heartbeat');
  $('#tab-queue').classList.toggle('on', t==='queue');
  $('#tab-configuration').classList.toggle('on', t==='configuration');
  $('#tab-telegram-relay').classList.toggle('on', t==='telegram-relay');
  $('#tab-runtime').classList.toggle('on', t==='runtime');
  $('#tab-users').classList.toggle('on', t==='users');
  $('#j-showdone').classList.toggle('hide', t!=='jobs');     // 各标签专属按钮
  $('#w-order').classList.toggle('hide', t!=='wxbot');
  $('#w-kind').classList.toggle('hide', t!=='wxbot');
  $('#q-state').classList.toggle('hide', t!=='queue');
  $('#q-state').value=state.qState;
  $('#c-search').classList.toggle('hide', t!=='configuration');
  if(t==='workflow'){
    $('#list').innerHTML='';if(workflowReady())startWorkflow();else renderWorkflowUnavailable();
  } else if(t==='telegram-relay'){
    $('#list').innerHTML='';$('#pane').innerHTML='<div class="empty">载入转发设置…</div>';loadTelegramRelay();
  } else if(t==='users'){
    $('#list').innerHTML='';$('#pane').innerHTML='<div class="empty">载入用户…</div>';loadUsers();
  } else if(t==='runtime'){
    $('#list').innerHTML='';$('#pane').innerHTML='<div class="empty">载入运行记录…</div>';loadRuntime();
  } else if(t==='queue'){
    $('#list').innerHTML='';$('#pane').innerHTML='<div class="empty">载入队列…</div>';loadQueue();
  } else if(t==='configuration'){
    if(state.cdata){renderConfigurationNav();renderConfigurationPane();}
    else{$('#list').innerHTML='';$('#pane').innerHTML='<div class="empty">载入配置…</div>';}
    loadConfiguration();
  } else if(t==='jobs'){
    $('#pane').innerHTML = '<div class="empty">载入中…</div>';
    loadJobs();
  } else if(t==='groups'){
    $('#pane').innerHTML = '<div class="empty">载入中…</div>';
    loadGroups();
  } else if(t==='heartbeat'){
    $('#pane').innerHTML = '<div class="empty">载入心跳配置…</div>';
    loadHeartbeat();
  } else {
    $('#pane').innerHTML = '<div class="empty">载入中…</div>';
    loadWxbot();
  }
}
$('#tab-wxbot').onclick = ()=>switchTab('wxbot');
$('#tab-workflow').onclick = ()=>switchTab('workflow');
$('#tab-jobs').onclick = ()=>switchTab('jobs');
$('#tab-groups').onclick = ()=>switchTab('groups');
$('#tab-heartbeat').onclick = ()=>switchTab('heartbeat');
$('#tab-queue').onclick = ()=>switchTab('queue');
$('#tab-configuration').onclick = ()=>switchTab('configuration');
$('#tab-telegram-relay').onclick = ()=>switchTab('telegram-relay');
$('#tab-runtime').onclick = ()=>switchTab('runtime');
$('#tab-users').onclick = ()=>switchTab('users');
$('#q-state').onchange=()=>{state.qState=$('#q-state').value;resetQueuePages();loadQueue();};
$('#c-search').oninput=()=>{state.cSearch=$('#c-search').value;renderConfigurationNav();renderConfigurationPane();};

$('#w-order').onclick = ()=>{
  state.wOrder = state.wOrder==='desc' ? 'asc' : 'desc';
  $('#w-order').textContent = '排序：'+(state.wOrder==='desc'?'倒序（新→旧）':'正序（旧→新）');
  savePreference('order',state.wOrder);state.wFlowOffset=0;loadWxbot();
};
$('#w-kind').onchange = ()=>{ state.wKind = $('#w-kind').value; renderWxPane(); };
$('#j-showdone').onclick = ()=>{                       // 默认隐藏「已完成」任务
  state.jobShowDone = !state.jobShowDone;
  $('#j-showdone').textContent = state.jobShowDone ? '隐藏已完成' : '显示已完成';
  $('#j-showdone').classList.toggle('on', state.jobShowDone);
  if(state.jobs){ renderJobsNav(); renderJobs(); }
};

function refreshCurrent(){
  if(state.tab==='workflow'){if(workflowReady())loadWorkflow();else renderWorkflowUnavailable();}
  else if(state.tab==='runtime') loadRuntime();
  else if(state.tab==='users') loadUsers();
  else if(state.tab==='queue') loadQueue();
  else if(state.tab==='configuration') loadConfiguration();
  else if(state.tab==='telegram-relay') loadTelegramRelay();
  else if(state.tab==='jobs') loadJobs();
  else if(state.tab==='groups') loadGroups();
  else if(state.tab==='heartbeat') loadHeartbeat();
  else loadWxbot();
}
$('#b-refresh').onclick = refreshCurrent;
$('#b-expand').onclick=()=>expandPage(true);
$('#b-collapse').onclick=()=>expandPage(false);
function renderCurrentCached(){
  if(state.tab==='workflow'){if(workflowReady())renderWorkflow(true);else renderWorkflowUnavailable();}
  else if(state.tab==='runtime')renderRuntime();
  else if(state.tab==='users'){userAdmin.query=state.viewSearch.users||'';userAdmin.offset=0;loadUsers();}
  else if(state.tab==='queue')renderQueuePane();
  else if(state.tab==='jobs'&&state.jobs){renderJobsNav();renderJobs();}
  else if(state.tab==='groups'&&state.gdata){renderGroupsNav();renderGroupsPane();}
  else if(state.tab==='heartbeat')renderHeartbeatPane();
  else if(state.tab==='telegram-relay')renderTelegramRelay();
  else if(state.tab==='wxbot')renderWxPane();
}
$('#view-search').oninput=()=>{state.viewSearch[state.tab]=$('#view-search').value;renderCurrentCached();};
let listCollapsed=false;
function setListCollapsed(value){
  listCollapsed=value;
  document.body.classList.toggle('list-collapsed',value);
  document.body.classList.toggle('list-open',!value);
  $('#b-contacts').textContent=value?'展开列表':'收起列表';
  $('#b-contacts').setAttribute('aria-expanded',String(!value));
}
$('#b-contacts').onclick=()=>{setListCollapsed(!listCollapsed);savePreference('listCollapsed',listCollapsed);};
$('#b-auto').onclick = ()=>{
  state.auto = state.auto?0:15;
  $('#b-auto').textContent = '自动刷新：'+(state.auto?state.auto+'s':'关');
  $('#b-auto').classList.toggle('on', !!state.auto);
  clearInterval(state.timer);
  if(state.auto) state.timer = setInterval(()=>{if(state.tab!=='workflow')refreshCurrent();}, state.auto*1000);
};

async function boot(){
  state.wOrder=readPreference('order','desc')==='asc'?'asc':'desc';
  const narrow=window.matchMedia('(max-width:900px)');
  setListCollapsed(narrow.matches||readPreference('listCollapsed',false));
  narrow.addEventListener('change',event=>setListCollapsed(event.matches||readPreference('listCollapsed',false)));
  $('#w-kind').value=state.wKind;
  $('#q-state').value=state.qState;
  const qp = new URLSearchParams(location.search);
  if(qp.get('kind')){ state.wKind = qp.get('kind'); $('#w-kind').value = state.wKind; }
  if(qp.get('worder')==='asc')state.wOrder='asc';
  $('#w-order').textContent='排序：'+(state.wOrder==='asc'?'正序（旧→新）':'倒序（新→旧）');
  const tab = qp.get('tab') || 'workflow';
  switchTab(['workflow','wxbot','jobs','groups','heartbeat','queue','configuration','runtime','users','telegram-relay'].includes(tab)?tab:'workflow');
}
// Preserve manual disclosures, focus and scroll during refreshes and form rerenders.
renderWxPane=preservingPane(renderWxPane);
renderJobs=preservingPane(renderJobs);
renderGroupsPane=preservingPane(renderGroupsPane);
renderHeartbeatPane=preservingPane(renderHeartbeatPane);
renderQueuePane=preservingPane(renderQueuePane);
renderConfigurationPane=preservingPane(renderConfigurationPane);
renderRuntime=preservingPane(renderRuntime);
if(workflowReady())renderWorkflow=preservingPane(renderWorkflow);
boot();
