const relayAdmin={data:null,draft:null,version:'',request:0,busy:false,error:'',message:''};
const relayLabels={enabled:'启用监听',include_text:'保留正文',include_images:'图片继续投递到微信',include_source:'保留来源',include_time:'保留原发布时间',window_title:'Telegram 窗口标题',bot_username:'现有机器人用户名',bot_id:'现有机器人数字 ID',poll_interval:'轮询间隔（秒）',album_quiet_seconds:'图集静默等待（秒）',max_album_wait:'图集最长等待（秒）'};
function relayCopy(value){return JSON.parse(JSON.stringify(value));}
function relayDraft(){
  if(!relayAdmin.draft&&relayAdmin.data){relayAdmin.draft=relayCopy(relayAdmin.data.settings);relayAdmin.version=relayAdmin.data.version;}
  return relayAdmin.draft;
}
async function loadTelegramRelay(){
  const request=++relayAdmin.request;
  try{
    const payload=await get('/api/telegram-relay');
    if(request!==relayAdmin.request)return;
    relayAdmin.data=payload;relayAdmin.error='';
  }catch(error){if(request!==relayAdmin.request)return;relayAdmin.error=error.message;}
  if(state.tab==='telegram-relay')renderTelegramRelay();
}
function relayRuntime(runtime){
  if(!runtime||runtime.state==='unavailable')return '<p class="muted">暂无运行快照；配置开关不代表服务已运行。</p>';
  const counts=Object.entries(runtime.counts||{}).map(([key,value])=>`${esc(key)}：${esc(value)}`).join(' · ');
  const channels=Array.isArray(runtime.channels)?runtime.channels:Object.entries(runtime.channels||{}).map(([key,value])=>({key,...(typeof value==='object'?value:{state:value})}));
  return `<p>当前阶段：${esc(runtime.phase||'等待扫描')} · 最近更新：${esc(typeof runtime.at==='number'?full(runtime.at):runtime.at||'未知')}</p><p>${counts}</p>${runtime.error?`<p class="bad">${esc(runtime.error)}</p>`:''}${channels.map(channel=>`<div class="card"><strong>${esc(channel.name||channel.key||'频道')}</strong><div>${esc(channel.phase||channel.state||channel.status||'等待扫描')}</div><div class="muted">最近扫描：${esc(channel.last_scan||channel.scanned_at||'暂无')} ${esc(channel.error||'')}</div></div>`).join('')}`;
}
function relayReviewTasks(runtime,cfg){
  const tasks=Array.isArray(runtime?.tasks)?runtime.tasks:[];
  const hold=runtime?.ui_hold?'<p class="bad" role="status">桌面已暂停，等待人工核对。重启或暂停／恢复不会解除此状态。</p>':'';
  if(!tasks.length&&!hold)return '';
  const names=new Map((cfg.channels||[]).map(channel=>[channel.key,channel.name]));
  return `<div class="card"><h3>转发任务与人工核对</h3>${hold}<p>先核对 Telegram 机器人实际收件及对应来源，再清理 Telegram 残留搜索、菜单和转发弹层。确认未发送后才可重试，避免重复转发。确认已转发仅记录 Telegram 阶段，不代表微信已送达。</p>${tasks.slice(0,50).map(task=>{
    const id=String(task.id||''),desktop=id==='desktop';
    const review=['blocked','uncertain'].includes(task.state)&&(desktop||/^[a-f0-9]{32}$/.test(id));
    const controls=review?`<label><input type="checkbox" id="relay-ack-${esc(id)}"> 我已核实此任务的发送结果，并清理 Telegram 残留界面</label><div>${desktop?'':`<button data-relay-resolve="${esc(id)}" data-relay-action="forwarded">确认已转发</button> `}<button data-relay-resolve="${esc(id)}" data-relay-action="retry">${desktop?'界面已清理，继续':'确认未发，重试'}</button> <button data-relay-resolve="${esc(id)}" data-relay-action="cancelled">${desktop?'界面已清理，放弃本次操作':'放弃'}</button></div>`:'';
    return `<div class="card"><strong>${esc(desktop?'桌面界面核对':names.get(task.channel)||task.channel||'未知频道')}</strong><p>频道键：${esc(task.channel||'未知')} · 消息 ID：${esc(desktop?'无消息任务':task.source_id||'尚未取得，请核对来源')}<br>任务 ID：${esc(id)} · 状态：${esc(task.state||'未知')} · ${task.submitted?'曾进入提交阶段':'尚无提交标记'}<br>更新时间：${esc(typeof task.updated==='number'?full(task.updated):task.updated||'未知')}</p>${task.error?`<p class="bad">${esc(task.error)}</p>`:''}${controls}</div>`;
  }).join('')}</div>`;
}
function renderTelegramRelay(){
  if(state.tab!=='telegram-relay')return;
  $('#list').innerHTML='<div class="head"><h2>Telegram 转发</h2><p class="muted">频道 → 现有机器人 → 新闻分组 → 微信</p></div>';
  if(!relayAdmin.data){$('#pane').innerHTML=`<div class="empty">${esc(relayAdmin.error||'载入转发设置…')}</div>`;return;}
  const cfg=relayAdmin.draft||relayAdmin.data.settings;
  const flags=['enabled','include_text','include_images','include_source','include_time'].map(key=>`<label><input type="checkbox" data-relay-field="${key}" ${cfg[key]?'checked':''} ${relayAdmin.busy?'disabled':''}> ${relayLabels[key]}</label>`).join(' ');
  const fields=['window_title','bot_username','bot_id','poll_interval','album_quiet_seconds','max_album_wait'].map(key=>`<label style="display:block;margin:10px 0">${relayLabels[key]}<input style="display:block;width:100%;box-sizing:border-box" data-relay-field="${key}" type="${['bot_id','poll_interval','album_quiet_seconds','max_album_wait'].includes(key)?'number':'text'}" value="${esc(cfg[key])}" ${relayAdmin.busy?'disabled':''}></label>`).join('');
  const channels=cfg.channels.map((channel,index)=>`<tr><td><input aria-label="频道启用" type="checkbox" data-relay-channel="${index}" data-relay-key="enabled" ${channel.enabled?'checked':''}></td>${['key','name','username','chat_id'].map(key=>`<td><input aria-label="${{key:'稳定频道键',name:'频道名称',username:'频道用户名',chat_id:'频道数字 ID'}[key]}" data-relay-channel="${index}" data-relay-key="${key}" value="${esc(channel[key]??'')}" type="${key==='chat_id'?'number':'text'}" style="width:100%;box-sizing:border-box"></td>`).join('')}<td><button data-relay-remove="${index}">删除</button></td></tr>`).join('');
  $('#pane').innerHTML=`<div class="head"><h2>Telegram 频道转发</h2><p>${esc(relayAdmin.data.note)}</p><p>目标用户名和数字 ID 必须与当前接收机器人的身份一致。管理员名单之外的会话不能通过 Skill 暂停或恢复。</p></div><div class="card"><h3>监听与内容</h3><div>${flags}</div>${fields}<label>允许使用管理 Skill 的微信会话（每行一个）<textarea data-relay-admins style="display:block;width:100%;box-sizing:border-box" rows="3">${esc(cfg.admin_contacts.join('\n'))}</textarea></label><p class="muted">首次历史：只建立基线；图片失败：保留待处理。</p></div><div class="card"><h3>频道列表</h3><p class="muted">稳定频道键用于保存游标，修改显示名称请保留此键。启用频道需提供用户名或数字 ID。</p><div style="overflow:auto"><table><thead><tr><th>启用</th><th>稳定频道键</th><th>名称</th><th>用户名</th><th>数字 ID</th><th></th></tr></thead><tbody>${channels}</tbody></table></div><button id="relay-add" ${relayAdmin.busy?'disabled':''}>新增频道</button></div><details class="card" data-detail="relay-selectors"><summary>Telegram 控件校准</summary><p class="muted">由管理员填写控件名称；无法确认窗口或来源时，监听会停留在待校准状态。</p><textarea data-relay-desktop style="display:block;width:100%;box-sizing:border-box" rows="8" spellcheck="false">${esc(JSON.stringify(cfg.desktop,null,2))}</textarea></details><div class="card"><p role="status" id="relay-message">${esc(relayAdmin.error||relayAdmin.message)}</p><button id="relay-save" ${relayAdmin.busy?'disabled':''}>${relayAdmin.busy?'保存中…':'保存设置'}</button> <button id="relay-discard" ${relayAdmin.busy?'disabled':''}>放弃草稿并刷新</button></div><div class="card"><h3>运行与队列状态</h3>${relayRuntime(relayAdmin.data.runtime)}</div>`;
  $('#pane').innerHTML+=relayReviewTasks(relayAdmin.data.runtime,cfg);
  $('#pane').querySelectorAll('[data-relay-resolve]').forEach(button=>button.onclick=()=>resolveTelegramRelay(button.dataset.relayResolve,button.dataset.relayAction));
  $('#pane').querySelectorAll('[data-relay-field]').forEach(input=>input.oninput=()=>{const key=input.dataset.relayField;relayDraft()[key]=input.type==='checkbox'?input.checked:input.type==='number'?Number(input.value):input.value;});
  $('#pane').querySelectorAll('[data-relay-channel]').forEach(input=>input.oninput=()=>{const channel=relayDraft().channels[Number(input.dataset.relayChannel)],key=input.dataset.relayKey;channel[key]=key==='enabled'?input.checked:key==='chat_id'?Number(input.value):input.value;});
  $('#pane').querySelectorAll('[data-relay-remove]').forEach(button=>button.onclick=()=>{relayDraft().channels.splice(Number(button.dataset.relayRemove),1);renderTelegramRelay();});
  $('[data-relay-admins]').oninput=event=>{relayDraft().admin_contacts=event.target.value.split('\n').map(v=>v.trim()).filter(Boolean);};
  $('[data-relay-desktop]').oninput=event=>{relayDraft();relayAdmin.desktopText=event.target.value;};
  if(relayAdmin.desktopText!==undefined)$('[data-relay-desktop]').value=relayAdmin.desktopText;
  $('#relay-add').onclick=()=>{relayDraft().channels.push({key:'',name:'',username:'',chat_id:0,enabled:false});renderTelegramRelay();};
  $('#relay-save').onclick=saveTelegramRelay;
  $('#relay-discard').onclick=()=>{relayAdmin.draft=null;relayAdmin.desktopText=undefined;relayAdmin.error='';relayAdmin.message='';loadTelegramRelay();};
  if(relayAdmin.busy)$('#pane').querySelectorAll('input,textarea,button').forEach(node=>node.disabled=true);
}
async function saveTelegramRelay(){
  if(relayAdmin.busy)return;
  const draft=relayDraft();
  try{if(relayAdmin.desktopText!==undefined)draft.desktop=JSON.parse(relayAdmin.desktopText);}
  catch{relayAdmin.error='控件校准需为有效的 JSON 对象；草稿已保留';renderTelegramRelay();return;}
  relayAdmin.busy=true;relayAdmin.error='';relayAdmin.message='';renderTelegramRelay();
  try{
    const response=await fetch('/api/telegram-relay',{method:'POST',headers:{'Content-Type':'application/json','X-Wxbot-Relay-Action':'1'},body:JSON.stringify({settings:draft,version:relayAdmin.version})});
    const payload=await response.json();if(!response.ok)throw new Error(payload.error||'保存失败');
    relayAdmin.data=payload;relayAdmin.draft=null;relayAdmin.desktopText=undefined;relayAdmin.message='已保存，现有服务下次读取生效。';
  }catch(error){relayAdmin.error=error.message;}
  finally{relayAdmin.busy=false;if(state.tab==='telegram-relay')renderTelegramRelay();}
}
async function resolveTelegramRelay(id,action){
  if(relayAdmin.busy)return;
  if(!$('#relay-ack-'+id)?.checked){
    relayAdmin.error='请先核对发送结果、清理 Telegram 残留界面，并勾选此任务的确认框。';
    const message=$('#relay-message');if(message)message.textContent=relayAdmin.error;return;
  }
  relayAdmin.busy=true;relayAdmin.error='';relayAdmin.message='';renderTelegramRelay();
  try{
    const response=await fetch('/api/telegram-relay/resolve',{method:'POST',headers:{'Content-Type':'application/json','X-Wxbot-Relay-Action':'1'},body:JSON.stringify({id,action,acknowledge:true})});
    const payload=await response.json();if(!response.ok)throw new Error(payload.error||'任务核对失败');
    relayAdmin.message='核对结果已提交；正在刷新运行状态。';await loadTelegramRelay();
  }catch(error){relayAdmin.error=error.message;}
  finally{relayAdmin.busy=false;if(state.tab==='telegram-relay')renderTelegramRelay();}
}
