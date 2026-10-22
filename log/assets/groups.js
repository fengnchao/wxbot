/* ---------------- 用户分组（messageType → 绑定用户） ---------------- */
async function postJSON(u, body){
  const r = await fetch(u, {method:'POST', headers:{'Content-Type':'application/json'},
                            body: JSON.stringify(body)});
  return r.json();
}

async function loadGroups(){
  const request=++state.gRequest;
  try{
    const data=await get('/api/groups');if(request!==state.gRequest||state.tab!=='groups')return;state.gdata=data;
    state.gError = '';
  }catch(e){
    if(state.tab!=='groups') return;
    $('#pane').innerHTML = '<div class="empty">载入失败：'+esc(e.message||e)+'</div>';
    return;
  }
  if(state.tab!=='groups') return;
  renderGroupsNav();
  renderGroupsPane();
}

function newsConfigCard(){
  const news=state.gdata?.news;
  if(!news)return '<div class="news-settings"><p class="muted">新闻配置接口尚未加载，请手动重启 log 服务后刷新。</p></div>';
  if(news.error)return `<div class="news-settings"><p class="warn">${esc(news.error)}</p><code>${esc(news.file)}</code></div>`;
  const values=state.gNewsDraft||news.settings;
  const choices=(items,key)=>items.map(item=>`<label class="news-choice">
    <input type="checkbox" data-news-field="${key}" value="${esc(item.id)}" ${values[key].includes(item.id)?'checked':''} ${state.gNewsBusy?'disabled':''}>
    <span>${esc(item.label)}${item.description?`<small>${esc(item.description)}</small>`:''}</span></label>`).join('');
  const status={sent:'已发送',incomplete:'部分未确认，请检查收发队列',no_news:'没有可用的新新闻',no_subscribers:'没有新闻订阅者',legacy_run_exists:'今日模拟任务已有记录，跳过重复推送',failed:'执行失败'};
  const latest=news.latest;
  return `<section class="news-settings" aria-label="新闻推送设置">
    <div class="news-title"><h3>新闻推送设置</h3><span class="tag">${esc(news.schedule)}</span></div>
    <p class="muted">${esc(news.note)}</p>
    <fieldset ${state.gNewsBusy?'disabled':''}><legend>新闻类型 · 可多选</legend><div class="news-choices">${choices(news.categories,'categories')}</div></fieldset>
    <fieldset ${state.gNewsBusy?'disabled':''}><legend>新闻来源 · 可多选</legend><div class="news-choices news-sources">${choices(news.sources,'sources')}</div>
      <p class="muted">首批来源为中新网官方 RSS 频道；重叠报道会去重，不足设定条数时按实际数量发送。</p></fieldset>
    <div class="news-actions"><label for="news-count">每日新闻条数</label>
      <input id="news-count" data-news-field="count" type="number" min="1" max="10" step="1" value="${esc(values.count)}" ${state.gNewsBusy?'disabled':''}>
      <span class="muted">1～10 条；较长简报会分段发送</span></div>
    <div class="news-actions"><button id="news-save" class="wx" ${state.gNewsBusy?'disabled':''}>${state.gNewsBusy?'保存中…':'保存新闻设置'}</button>
      <button id="news-cancel" ${!state.gNewsDraft||state.gNewsBusy?'disabled':''}>取消修改</button>
      <span class="news-feedback" role="status">${state.gNewsDraft?'有未保存修改 · ':''}${esc(state.gNewsMessage)}</span></div>
    <p class="warn" id="news-error" role="alert">${esc(state.gNewsError)}</p>
    ${latest?`<div class="news-last">最近执行：${esc(latest.date)} · ${esc(status[latest.status]||latest.status)} · 新闻 ${Number(latest.article_count)||0} 条 · 已完成 ${Number(latest.sent)||0} 人</div>`:''}
    <details class="diagnostic" data-detail="news-settings-file"><summary>配置文件与生效方式</summary>
      <code>${esc(news.file)}</code><p>保存后下次任务读取，无需重启 Butler 或 wxbot；不会立即发送新闻。</p></details>
  </section>`;
}

function bindNewsForm(){
  $('#pane').querySelectorAll('[data-news-field]').forEach(input=>{
    const remember=()=>{
    const news=state.gdata.news;
    if(!state.gNewsDraft)state.gNewsVersion=news.version;
    state.gNewsDraft={categories:Array.from($('#pane').querySelectorAll('[data-news-field="categories"]:checked'),x=>x.value),
      sources:Array.from($('#pane').querySelectorAll('[data-news-field="sources"]:checked'),x=>x.value),
      count:Number($('#news-count').value)};
    state.gNewsMessage='';state.gNewsError='';
    const feedback=$('#pane').querySelector('.news-feedback');if(feedback)feedback.textContent='有未保存修改';
    const error=$('#news-error');if(error)error.textContent='';
    $('#news-cancel').disabled=false;
    };
    if(input.type==='number')input.oninput=remember;else input.onchange=remember;
  });
  const save=$('#news-save');if(save)save.onclick=saveNewsConfig;
  const cancel=$('#news-cancel');if(cancel)cancel.onclick=()=>{
    state.gNewsDraft=null;state.gNewsMessage='';state.gNewsError='';renderGroupsPane();
  };
}

async function saveNewsConfig(){
  if(state.gNewsBusy)return;
  const news=state.gdata?.news, settings=state.gNewsDraft||news?.settings;
  if(!settings)return;
  if(!settings.categories.length||!settings.sources.length||!Number.isInteger(settings.count)||settings.count<1||settings.count>10){
    state.gNewsError='请至少选择一种新闻类型、一个新闻来源，并填写 1～10 的整数条数';renderGroupsPane();return;
  }
  state.gNewsBusy=true;state.gNewsError='';state.gNewsMessage='';renderGroupsPane();
  try{
    const response=await fetch('/api/news-config',{method:'POST',headers:{'Content-Type':'application/json','X-Wxbot-Config-Action':'1'},
      body:JSON.stringify({settings,version:state.gNewsDraft?state.gNewsVersion:news.version})});
    const result=await response.json();
    if(!response.ok||!result.ok)throw new Error(result.error||'保存失败');
    ++state.gRequest;state.gdata.news=result.news;state.gNewsDraft=null;
    state.gNewsMessage='已保存，下次新闻任务生效';
  }catch(error){state.gNewsError=String(error.message||error);}
  finally{state.gNewsBusy=false;if(state.tab==='groups')renderGroupsPane();}
}

function renderGroupsNav(){
  const d = state.gdata, el = $('#list');
  const total = d.message_types.reduce((a,t)=>a+t.count, 0);
  el.innerHTML = `<div class="user ${state.gUid==='all'?'sel':''}" data-g="all">
      <div class="nm">全部类型</div>
      <div class="st"><span>类型 <b>${d.message_types.length}</b></span><span>绑定合计 ${total}</span></div>
      <div class="pv">绑定字典：收到群发消息按类型推给绑定的用户</div>
    </div>` + d.message_types.map(t=>`
    <div class="user ${state.gUid===String(t.type)?'sel':''}" data-g="${t.type}">
      <div class="nm">${esc(t.label)} <span class="tag">type=${t.type}</span></div>
      <div class="st"><span>绑定用户 <b>${t.count}</b></span></div>
      <div class="pv">${t.users.length? esc(t.users.join('、')) : '（未绑定）'}</div>
    </div>`).join('');
  el.querySelectorAll('.user').forEach(n=>n.onclick=()=>{
    state.gUid = n.dataset.g;
    if(state.gUid!=='all') state.gOpen[state.gUid] = true;
    el.querySelectorAll('.user').forEach(x=>x.classList.toggle('sel', x.dataset.g===state.gUid));
    renderGroupsPane();
  });
}

function gCard(t){
  const open = state.gUid==='all' ? !!state.gOpen[String(t.type)] : true;
  const chips = t.members.map(m=>`<span class="chip gchip">${esc(m.name)}${m.label?` <span class="k2">${esc(m.label)}</span>`:''}${m.known?'':' <span class="k2">（不在绑定清单）</span>'} <button class="gx" data-t="${t.type}" data-u="${esc(m.name)}" title="解除绑定">✕</button></span>`).join('');
  const bound = new Set(t.users);
  const free = (state.gdata.contacts||[]).filter(c=>!bound.has(c.name));
  const opts = free.map(c=>`<option value="${esc(c.name)}">${esc(c.name)}${c.label?`（${esc(c.label)}）`:''}</option>`).join('');
  return `<div class="gcard ${open?'open':''}" data-t="${t.type}">
    <div class="gh" data-t="${t.type}">
      <span class="gcaret">${open?'▾':'▸'}</span>
      <span class="gt">${esc(t.label)}</span>
      <span class="gn">messageType = ${t.type}</span>
      <span class="gc">绑定 <b>${t.count}</b> 人</span>
      <span style="flex:1"></span>
      <span class="gn">${t.users.length? esc(t.users.join('、')) : ''}</span>
    </div>
    <div class="gb">
      <div>${chips || '<div class="gempty">还没有绑定用户 —— 收到该类型的群发消息时不会推送给任何人</div>'}</div>
      <div class="gadd">
        <select id="gsel-${t.type}">${opts || '<option value="">（没有可选的已绑定联系人）</option>'}</select>
        <input type="text" id="gtxt-${t.type}" placeholder="或直接输入微信窗口标题">
        <button class="wx" data-add="${t.type}">绑定</button>
      </div>
      ${Number(t.type)===1?newsConfigCard():''}
    </div>
  </div>`;
}

function renderGroupsPane(){
  const d = state.gdata;
  if(!d){ $('#pane').innerHTML='<div class="empty">载入中…</div>'; return; }
  const types = d.message_types.filter(t=>(state.gUid==='all'||String(t.type)===state.gUid)&&matchesQuery(t.label,t.type,t.users.join(' ')));
  const total = d.message_types.reduce((a,t)=>a+t.count, 0);
  const head = `<div class="head">
    <h2>用户分组 · messageType → 绑定用户（群发按此字典投递）
      </h2><details class="diagnostic" data-detail="groups-source"><summary>诊断详情 · 分组文件</summary><code>${esc(d.file)}</code></details>
    <div class="kv">
      <span>类型 <b>${d.message_types.length}</b></span>
      <span>绑定合计 <b>${total}</b></span>
      <span>可选联系人 <b>${(d.contacts||[]).length}</b></span>
      <span>字典更新 <b>${esc(d.updated_at||'-')}</b></span>
      <span class="k">1=新闻消息 2=问候消息 3=其他</span>
      <span style="flex:1"></span>
      ${state.gError?`<span class="warn">${esc(state.gError)}</span>`:''}
    </div></div>`;
  $('#pane').innerHTML = head + (types.length
      ? types.map(gCard).join('') : '<div class="empty">没有该类型</div>');
  $('#pane').querySelectorAll('.gh').forEach(n=>n.onclick=()=>{
    const t = n.dataset.t;
    state.gOpen[t] = !state.gOpen[t];
    renderGroupsPane();
  });
  $('#pane').querySelectorAll('.gx').forEach(n=>n.onclick=(e)=>{
    e.stopPropagation();
    gMutate('unbind', n.dataset.t, n.dataset.u);
  });
  $('#pane').querySelectorAll('[data-add]').forEach(n=>n.onclick=()=>{
    const t = n.dataset.add;
    const sel = $('#pane').querySelector('#gsel-'+t), txt = $('#pane').querySelector('#gtxt-'+t);
    const name = ((txt && txt.value) || '').trim() || ((sel && sel.value) || '').trim();
    if(!name){ state.gError = '请先选择或输入要绑定的用户'; renderGroupsPane(); return; }
    gMutate('bind', t, name);
  });
  bindNewsForm();
}

async function gMutate(action, type, user){
  state.gError = '';
  try{
    const res = await postJSON('/api/groups', {action, type: Number(type), user});
    if(res && res.message_types){ state.gdata = res; }
    else { state.gError = '操作失败：'+((res && (res.error||res.detail)) || '未知原因'); }
  }catch(e){ state.gError = '操作失败：'+(e.message||e); }
  renderGroupsNav();
  renderGroupsPane();
}

/* ---------------- 心跳与角色 skill ---------------- */
