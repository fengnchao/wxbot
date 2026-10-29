async function loadConfiguration(force=false){
  if(!force&&!state.cRefreshNeeded&&(state.cDrafts.size||state.cBusy.size)) return;
  const request=++state.cRequest;
  try{
    const data=await apiGet('/api/configuration');
    if(request!==state.cRequest||state.tab!=='configuration') return;
    if(!force&&!state.cRefreshNeeded&&(state.cDrafts.size||state.cBusy.size)) return;
    // Keep the original file version and rows for every file with unsaved edits.
    if(state.cdata&&(state.cDrafts.size||state.cBusy.size)){
      const preserve=id=>state.cDrafts.has(id)||state.cBusy.has(id);
      data.sources=(data.sources||[]).filter(s=>!preserve(s.id)).concat((state.cdata.sources||[]).filter(s=>preserve(s.id)));
      data.sections=(data.sections||[]).filter(s=>!preserve(s.source_id)).concat((state.cdata.sections||[]).filter(s=>preserve(s.source_id)));
    }
    state.cdata=data;state.cError='';
    state.cRefreshNeeded=false;
  }catch(e){
    if(request!==state.cRequest||state.tab!=='configuration') return;
    state.cError=e.message||'配置载入失败';
  }
  renderConfigurationNav();renderConfigurationPane();
}
const CONFIG_EDITORS=['boolean','integer','number','string','json','secret'];
function configurationSource(id){return (state.cdata?.sources||[]).find(s=>s.id===id);}
function configurationEditable(source,row){
  return !!(source&&source.status!=='error'&&typeof source.version==='string'&&source.version&&
    row.editable===true&&Array.isArray(row.path)&&row.path.length&&CONFIG_EDITORS.includes(row.editor));
}
function configurationRaw(row){
  return row.editor==='secret'?'':typeof row.value==='string'?row.value:JSON.stringify(row.value,null,2)??'';
}
function configurationDraft(sourceId,row){return state.cDrafts.get(sourceId)?.changes.get(JSON.stringify(row.path));}
function setConfigurationDraft(sourceId,row,raw,op='set'){
  const source=configurationSource(sourceId);
  if(state.cBusy.has(sourceId)||!configurationEditable(source,row)) return;
  if(op==='default'&&!row.default_available) return;
  if(op==='clear'&&row.editor!=='secret') return;
  if(!['set','clear','default','keep'].includes(op)) return;
  const key=JSON.stringify(row.path);
  const unchanged=op==='keep'||(op==='set'&&row.editor!=='secret'&&String(raw)===configurationRaw(row));
  if(unchanged){
    const draft=state.cDrafts.get(sourceId);
    if(draft){draft.changes.delete(key);if(!draft.changes.size)state.cDrafts.delete(sourceId);}
  }else{
    if(!state.cDrafts.has(sourceId))state.cDrafts.set(sourceId,{version:source.version,changes:new Map()});
    state.cDrafts.get(sourceId).changes.set(key,{path:row.path.slice(),op,raw:String(raw??''),row});
  }
  state.cMessages.delete(sourceId);
  updateConfigurationStatus();
}
function cancelConfigurationSource(sourceId){
  if(state.cBusy.has(sourceId))return;
  state.cDrafts.delete(sourceId);state.cMessages.delete(sourceId);
  if(state.tab==='configuration'){renderConfigurationNav();renderConfigurationPane();}
}
function configurationChanges(draft){
  return Array.from(draft.changes.values(),change=>{
    const {row,op,raw,path}=change;
    const item={path,op};
    if(op!=='set')return item;
    let value=raw;
    const fail=message=>{throw new Error(`${row.label||row.key}：${message}`);};
    if(row.editor==='secret'&&!raw.trim())fail('替换密钥不能为空，请填写新密钥或选择「保持不变」。');
    if(row.editor==='boolean'){
      if(!['true','false'].includes(raw))fail('请选择开启或关闭。');
      value=raw==='true';
    }else if(['integer','number'].includes(row.editor)){
      value=Number(raw);
      if(!raw.trim()||!Number.isFinite(value)||(row.editor==='integer'&&!Number.isInteger(value)))fail(row.editor==='integer'?'请输入整数。':'请输入有效数值。');
    }else if(row.editor==='json'){
      try{value=JSON.parse(raw);}catch{fail('格式不正确，请输入有效 JSON。');}
    }
    item.value=value;return item;
  });
}
function configurationStatus(sourceId){
  if(state.cBusy.has(sourceId))return {text:'正在保存…'};
  const message=state.cMessages.get(sourceId);
  if(message)return message;
  const count=state.cDrafts.get(sourceId)?.changes.size||0;
  return {text:count?`${count} 项未保存 · 草稿仅保存在当前页面内存中`:'没有未保存的更改'};
}
function updateConfigurationStatus(){
  if(state.tab!=='configuration')return;
  const sources=state.cdata?.sources||[];
  $('#pane').querySelectorAll('[data-c-status]').forEach(el=>{
    const source=sources[Number(el.dataset.cStatus)],status=configurationStatus(source?.id);
    el.textContent=status.text;el.classList.toggle('warn',!!status.error);
  });
  $('#pane').querySelectorAll('[data-c-save]').forEach(el=>{
    const source=sources[Number(el.dataset.cSave)];
    el.disabled=!source||source.status==='error'||!source.version||!state.cDrafts.has(source.id)||state.cBusy.has(source.id);
  });
  $('#pane').querySelectorAll('[data-c-cancel]').forEach(el=>{
    const source=sources[Number(el.dataset.cCancel)];
    el.disabled=!source||!state.cDrafts.has(source.id)||state.cBusy.has(source.id);
  });
  $('#pane').querySelectorAll('[data-c-source]').forEach(el=>{
    const source=sources[Number(el.dataset.cSource)];
    el.classList.toggle('dirty',state.cDrafts.has(source.id));
    el.classList.toggle('has-message',state.cMessages.has(source.id));
  });
  const total=$('#c-dirty-count');if(total)total.textContent=Array.from(state.cDrafts.values()).reduce((n,d)=>n+d.changes.size,0)+' 项未保存';
}
async function reloadConfiguration(){
  if(state.cBusy.size)return;
  if(state.cDrafts.size&&!confirm('重新载入会放弃当前全部配置草稿，包括尚未保存的密钥替换。继续刷新？'))return;
  state.cDrafts.clear();state.cMessages.clear();state.cRefreshNeeded=true;
  await loadConfiguration(true);
}
async function saveConfigurationSource(sourceId){
  const source=configurationSource(sourceId),draft=state.cDrafts.get(sourceId);
  if(!source||source.status==='error'||!draft?.changes.size||state.cBusy.has(sourceId))return;
  let changes;
  try{changes=configurationChanges(draft);}
  catch(error){state.cMessages.set(sourceId,{text:error.message,error:true});if(state.tab==='configuration')renderConfigurationPane();return;}
  const summary=Array.from(draft.changes.values(),c=>`${c.row.label||c.row.key}（${c.row.key}）：${c.op==='default'?'恢复默认':c.op==='clear'?'清空密钥':'修改'}\n  生效：${c.row.effect||'按来源服务的配置规则生效'}`).join('\n');
  if(!confirm(`保存 ${source.title||source.id}\n\n${summary}\n\n保存后的生效与重启要求见以上提示。确认保存 ${changes.length} 项更改？`))return;
  state.cBusy.add(sourceId);state.cMessages.delete(sourceId);
  if(state.tab==='configuration')renderConfigurationPane();
  let saved=false;
  try{
    const response=await fetch('/api/configuration',{method:'POST',headers:{'Content-Type':'application/json','X-Wxbot-Config-Action':'1'},
      body:JSON.stringify({source:sourceId,version:draft.version,changes,acknowledge:true})});
    const data=await response.json();
    if(!response.ok||!data.ok){
      state.cMessages.set(sourceId,{text:(data.error||'保存失败')+(response.status===409?'；文件版本已变化，请点击「重新载入配置」刷新后重新编辑。':''),error:true});
    }else{
      state.cDrafts.delete(sourceId);state.cRefreshNeeded=true;saved=true;
      state.cMessages.set(sourceId,{text:(data.message||'已保存')+(data.restart?.length?'；需重启：'+data.restart.join('、'):'')});
    }
  }catch{state.cMessages.set(sourceId,{text:'保存请求失败，请检查连接后重试。',error:true});}
  finally{state.cBusy.delete(sourceId);}
  if(state.tab!=='configuration')return;
  if(saved)await loadConfiguration(true);
  else renderConfigurationPane();
}
function configurationMatches(section,row){
  const q=state.cSearch.trim().toLowerCase();
  return !q||[section.title,section.source,row.key,row.label,row.description,row.effect,row.sensitive?'':JSON.stringify(row.value)].join(' ').toLowerCase().includes(q);
}
const CONFIG_CATEGORIES=[['basic','基础连接'],['wechat','微信收发'],['model','模型后端'],['contacts','联系人与策略'],['logging','日志'],['advanced','高级配置']];
const CONFIG_HIDDEN_SECTIONS=new Set(['log','log.flow_trace','wxbot.typing','wxbot.failure_policy']);
function configuredBackend(){
  const rows=(state.cdata?.sections||[]).flatMap(s=>s.rows);
  return rows.find(r=>r.key==='butler.agent.provider')?.value||'hermes';
}
function compatibilityConfiguration(section,row){
  const id=section.id||'',backend=configuredBackend();
  return (id==='butler.hermes'&&backend!=='hermes')||(id==='butler.codex'&&backend!=='codex')||id==='butler.dispatch'||
    (id==='wxbot.model'&&row.path?.at(-1)!=='backend'&&(state.cdata?.sections||[]).flatMap(s=>s.rows).find(r=>r.key==='wxbot.model.backend')?.value==='butler');
}
function configurationCategory(section,row){
  const id=section.id||'',key=row.key||'';
  if(!row.editable||compatibilityConfiguration(section,row))return 'advanced';
  if(['directory','policies','log_policies','groups','log_groups'].includes(section.source_id)||key.startsWith('butler.contacts'))return 'contacts';
  if(id==='log_config'||id==='butler.log')return 'logging';
  if(['butler.codex','butler.hermes','wxbot.model'].includes(id))return 'model';
  if(['wxbot.butler','butler.server','butler.agent'].includes(id))return 'basic';
  if(['butler.heartbeat','butler.groups'].includes(id))return 'contacts';
  if(section.source_id==='wxbot')return 'wechat';
  return 'advanced';
}
function configurationSections(){
  const raw=(state.cdata?.sections||[]).filter(s=>!CONFIG_HIDDEN_SECTIONS.has(s.id));
  return raw.map(s=>({...s,rows:s.rows.filter(r=>configurationMatches(s,r)&&(state.cSearch.trim()||state.cSection==='all'||state.cSection===s.id||configurationCategory(s,r)===state.cSection))})).filter(s=>s.rows.length);
}
function configurationStructuredControl(row,raw,index,jsonControl,disabled){
  let values;try{values=JSON.parse(raw);}catch{return `<div class="warn">当前草稿格式无效，请在 JSON 编辑器中修正。</div>${jsonControl}`;}
  if(!Array.isArray(values))return jsonControl;
  if((row.widget==='contacts'&&values.some(v=>v===null||typeof v!=='object'||Array.isArray(v)))||
      (row.widget==='string-list'&&values.some(v=>typeof v!=='string'))){
    return `<div class="warn">列表条目格式不正确，请在 JSON 编辑器中修正后再保存。</div>${jsonControl}`;
  }
  let form='';
  if(row.widget==='string-list'){
    form=`<div class="list-editor">${values.map((v,i)=>`<div class="row"><input type="text" data-c-list="${index}" data-item="${i}" value="${esc(v)}" aria-label="${esc(row.label)} ${i+1}" ${disabled}><button data-c-remove="${index}" data-item="${i}" ${disabled}>移除</button></div>`).join('')}</div><button data-c-add="${index}" ${disabled}>添加一项</button>`;
  }else{
    const labels={name:'微信会话名称',uid:'唯一用户 ID',label:'显示名称',profile:'Profile',channel_type:'会话类型'};
    form=`<div class="contact-editor">${values.map((contact,i)=>`<div class="contact-row">${Object.entries(labels).map(([key,label])=>`<label>${label}${key==='channel_type'?`<select data-c-contact="${index}" data-item="${i}" data-field="${key}" aria-label="联系人 ${i+1} ${label}" ${disabled}><option value="dm" ${contact[key]!=='group'?'selected':''}>私聊</option><option value="group" ${contact[key]==='group'?'selected':''}>群聊</option></select>`:`<input type="text" data-c-contact="${index}" data-item="${i}" data-field="${key}" aria-label="联系人 ${i+1} ${label}" value="${esc(contact[key]||'')}" ${disabled}>`}</label>`).join('')}<div class="contact-actions"><button data-c-remove="${index}" data-item="${i}" ${disabled}>移除此联系人</button></div></div>`).join('')}</div><button data-c-add="${index}" ${disabled}>添加联系人</button>`;
  }
  return form+`<details data-detail="json:${esc(row.key)}"><summary>高级 JSON 编辑</summary>${jsonControl}</details>`;
}
function bindConfigurationStructuredControls(editors){
  const valuesFor=index=>{const {sourceId,row}=editors[index];return JSON.parse(configurationDraft(sourceId,row)?.raw??configurationRaw(row));};
  const change=(index,mutate,rerender=false)=>{
    const {sourceId,row}=editors[index];let values;try{values=valuesFor(index);}catch{return;}
    mutate(values,row);setConfigurationDraft(sourceId,row,JSON.stringify(values,null,2));
    if(rerender)renderConfigurationPane();
    else{
      const json=$('#pane').querySelector(`[data-c-editor="${index}"]`);if(json)json.value=JSON.stringify(values,null,2);
    }
  };
  $('#pane').querySelectorAll('[data-c-list]').forEach(el=>el.oninput=()=>change(Number(el.dataset.cList),values=>values[Number(el.dataset.item)]=el.value));
  $('#pane').querySelectorAll('[data-c-contact]').forEach(el=>{
    const handler=()=>change(Number(el.dataset.cContact),values=>values[Number(el.dataset.item)][el.dataset.field]=el.value);
    el.oninput=handler;el.onchange=handler;
  });
  $('#pane').querySelectorAll('[data-c-remove]').forEach(el=>el.onclick=()=>change(Number(el.dataset.cRemove),values=>values.splice(Number(el.dataset.item),1),true));
  $('#pane').querySelectorAll('[data-c-add]').forEach(el=>el.onclick=()=>change(Number(el.dataset.cAdd),(values,row)=>values.push(row.widget==='contacts'?{name:'',uid:'',profile:'default',channel_type:'dm'}:''),true));
}
function renderConfigurationNav(){
  const rows=(state.cdata?.sections||[]).filter(s=>!CONFIG_HIDDEN_SECTIONS.has(s.id)).flatMap(s=>s.rows.map(r=>({s,r})));
  $('#list').innerHTML=CONFIG_CATEGORIES.concat([['all','全部参数']]).map(([id,title])=>`<div class="user ${state.cSection===id?'sel':''}" data-c-category="${id}"><div class="nm">${title}</div><div class="st">${rows.filter(({s,r})=>(id==='all'||configurationCategory(s,r)===id)&&configurationMatches(s,r)).length} 项${id==='advanced'?' · 兼容配置':''}</div></div>`).join('');
  $('#list').querySelectorAll('[data-c-category]').forEach(el=>el.onclick=()=>{
    state.cSection=el.dataset.cCategory;panePositions.delete('configuration');renderConfigurationNav();renderConfigurationPane();$('#pane').scrollTop=0;
  });
}
function renderConfigurationPane(){
  const d=state.cdata;
  if(!d){ $('#pane').innerHTML=`<div class="empty warn">${esc(state.cError||'正在载入配置…')}</div>`; return; }
  const sections=configurationSections(),sources=d.sources||[],editors=[];
  const visibleSourceIds=new Set(sections.filter(s=>s.rows.some(r=>configurationMatches(s,r))).map(s=>s.source_id));
  const sourceActions=sources.map((s,i)=>{
      if(!visibleSourceIds.has(s.id)&&!state.cDrafts.has(s.id)&&!state.cMessages.has(s.id)&&!state.cBusy.has(s.id)&&s.status!=='error')return '';
      const status=configurationStatus(s.id),editable=!!s.version;
      return `<div data-c-source="${i}" class="source-actions ${state.cDrafts.has(s.id)?'dirty':''} ${state.cMessages.has(s.id)?'has-message':''} ${s.status==='error'?'source-error':''}"><strong>${esc(s.title)}</strong>
        <div class="config-actions">${editable?`<button data-c-save="${i}" class="wx" ${s.status!=='error'&&state.cDrafts.has(s.id)&&!state.cBusy.has(s.id)?'':'disabled'}>保存此文件</button><button data-c-cancel="${i}" ${state.cDrafts.has(s.id)&&!state.cBusy.has(s.id)?'':'disabled'}>取消更改</button>`:''}<span data-c-status="${i}" class="config-status ${status.error?'warn':''}">${esc(s.status==='error'?s.error:status.text)}</span></div>
        </div>`;
    }).join('');
  $('#pane').innerHTML=`<div class="head"><h2>${state.cSearch.trim()?'配置搜索结果':esc(CONFIG_CATEGORIES.find(([id])=>id===state.cSection)?.[1]||'全部配置')}</h2><div class="monitor-note">${esc(d.note)}</div>
    <p class="monitor-note">修改后点击保存；生效方式见各项提示。刷新页面会丢失未保存的修改。</p>
    ${state.cSection==='contacts'?'<div class="hbnote">角色、允许的 Skill 与心跳统一在 <button data-open-role>角色与心跳</button> 维护；分组在 <button data-open-groups>用户分组</button> 维护。下方保留底层参数入口。</div>':''}
    <button id="c-reload" ${state.cBusy.size?'disabled':''}>重新载入配置</button><span class="monitor-source"> 有草稿时会确认放弃更改</span>
    ${state.cError?`<div class="monitor-note warn">${esc(state.cError)}</div>`:''}
    ${(d.warnings||[]).map(w=>`<div class="monitor-note warn">${esc(w)}</div>`).join('')}
    </div>`+
    sections.map(s=>{
      const rows=s.rows.filter(r=>configurationMatches(s,r));
      if(!rows.length) return '';
      const advanced=rows.every(r=>configurationCategory(s,r)==='advanced')||['policies','log_policies','groups','log_groups'].includes(s.source_id);
      const compatibility=rows.some(r=>compatibilityConfiguration(s,r));
      return `<${advanced?'details':'div'} class="config-section" ${advanced?`data-detail="config:${esc(s.id)}"`:''}>${advanced?'<summary>':'<h3>'}${esc(s.title)}${compatibility?' · 未启用 / 兼容配置':''}${advanced?'</summary>':'</h3>'}`+
        rows.map(r=>{
          const source=configurationSource(s.source_id),editable=configurationEditable(source,r),draft=configurationDraft(s.source_id,r);
          let control=`<pre>${esc(typeof r.value==='string'?(r.value||'（空）'):JSON.stringify(r.value,null,2))}</pre>`;
          if(editable){
            const i=editors.push({sourceId:s.source_id,row:r})-1,disabled=state.cBusy.has(s.source_id)?'disabled':'';
            const raw=draft?.op==='set'?draft.raw:configurationRaw(r),attr=`class="config-editor" data-c-editor="${i}" data-focus-key="${esc(s.source_id+':'+r.key)}" aria-label="${esc(r.label||r.key)}" ${disabled}`;
            if(r.editor==='secret'){
              const mode=draft?.op||'keep';
              control=`<div class="monitor-source">${esc(r.value)} · 原密钥已隐藏</div><select data-c-secret="${i}" aria-label="${esc(r.label||r.key)}操作" ${disabled}><option value="keep" ${mode==='keep'?'selected':''}>保持不变</option><option value="set" ${mode==='set'?'selected':''}>替换密钥</option><option value="clear" ${mode==='clear'?'selected':''}>清空密钥</option></select><input ${attr} type="password" autocomplete="new-password" placeholder="选择替换后填写新密钥" ${mode==='set'?'':'disabled'}>`;
            }else if(r.choices?.length){
              const choices=[...new Set([...r.choices,...(raw&&!r.choices.includes(raw)?[raw]:[])])];
              control=`<select ${attr}>${choices.map(v=>`<option value="${esc(v)}" ${raw===v?'selected':''}>${esc(v)}</option>`).join('')}</select>`;
            }else if(r.editor==='boolean'){
              control=`<select ${attr}><option value="true" ${raw==='true'?'selected':''}>开启（true）</option><option value="false" ${raw==='false'?'selected':''}>关闭（false）</option></select>`;
            }else if(['integer','number'].includes(r.editor)){
              control=`<input ${attr} type="number" step="${r.editor==='integer'?'1':'any'}" value="${esc(raw)}">`;
            }else{
              if(r.editor==='string'&&!raw.includes('\n')&&raw.length<160){control=`<input ${attr} type="text" value="${esc(raw)}">`;}
              else control=`<textarea ${attr} rows="${r.editor==='json'?4:2}" spellcheck="false">${esc(raw)}</textarea>`;
              if(['string-list','contacts'].includes(r.widget))control=configurationStructuredControl(r,raw,i,control,disabled);
            }
            if(r.default_available)control+=`<button class="config-default" data-c-default="${i}" ${disabled}>恢复默认</button>`;
            if(draft?.op==='default')control+='<div class="monitor-source">待保存：恢复默认值</div>';
          }
          return `<div class="config-field"><div><div class="config-label">${esc(r.label||r.key.split('.').at(-1))}</div>${r.description?`<div class="monitor-note">${esc(r.description)}</div>`:''}${r.effect?`<div class="monitor-source">生效：${esc(r.effect)}</div>`:''}
</div><div class="config-control">${control}${r.sensitive?'<div class="monitor-source">密钥已隐藏</div>':''}</div></div>`;
        }).join('')+`</${advanced?'details':'div'}>`;
    }).join('');
  if(!sections.some(s=>s.rows.some(r=>configurationMatches(s,r)))){
    $('#pane').innerHTML+='<div class="empty">当前分类没有匹配配置，可清空搜索或选择左侧「全部配置」。</div>';
  }
  $('#pane').innerHTML+=`<div class="config-savebar"><strong id="c-dirty-count">${Array.from(state.cDrafts.values()).reduce((n,d)=>n+d.changes.size,0)} 项未保存</strong>${sourceActions}</div>`;
  $('#c-reload').onclick=reloadConfiguration;
  $('#pane').querySelectorAll('[data-c-save]').forEach(el=>el.onclick=()=>saveConfigurationSource(sources[Number(el.dataset.cSave)].id));
  $('#pane').querySelectorAll('[data-c-cancel]').forEach(el=>el.onclick=()=>cancelConfigurationSource(sources[Number(el.dataset.cCancel)].id));
  $('#pane').querySelectorAll('[data-c-editor]').forEach(el=>{
    const {sourceId,row}=editors[Number(el.dataset.cEditor)];
    if(row.editor==='secret')el.value=configurationDraft(sourceId,row)?.op==='set'?configurationDraft(sourceId,row).raw:'';
    el.oninput=()=>setConfigurationDraft(sourceId,row,el.value);
    el.onchange=()=>{setConfigurationDraft(sourceId,row,el.value);if(['string-list','contacts'].includes(row.widget))renderConfigurationPane();};
  });
  $('#pane').querySelectorAll('[data-c-secret]').forEach(el=>el.onchange=()=>{
    const {sourceId,row}=editors[Number(el.dataset.cSecret)];
    setConfigurationDraft(sourceId,row,'',el.value);renderConfigurationPane();
  });
  $('#pane').querySelectorAll('[data-c-default]').forEach(el=>el.onclick=()=>{
    const {sourceId,row}=editors[Number(el.dataset.cDefault)];
    setConfigurationDraft(sourceId,row,'','default');renderConfigurationPane();
  });
  bindConfigurationStructuredControls(editors);
  $('#pane').querySelectorAll('[data-open-role]').forEach(el=>el.onclick=()=>switchTab('heartbeat'));
  $('#pane').querySelectorAll('[data-open-groups]').forEach(el=>el.onclick=()=>switchTab('groups'));
}
