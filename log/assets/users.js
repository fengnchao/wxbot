// User and memory administration stays in page memory; the server owns credentials.
const userAdmin={rows:[],total:0,offset:0,limit:25,query:'',contact:'',channel:'',status:'',request:0,dialogEpoch:0,memory:null,memoryOffset:0,memoryQuery:'',auditOffset:0};

async function userRequest(path,payload){
  const response=await fetch(path,payload===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Wxbot-User-Action':'1'},body:JSON.stringify(payload)});
  const data=await response.json();
  if(!response.ok)throw new Error(data.error||`操作失败（HTTP ${response.status}）`);
  markRefreshed();return data;
}
function userStatus(row){return row.status==='disabled'?'已停用':row.status==='observed'?'待核对':'已确认';}
function userLabel(row){return row.channel_type==='group'?`${row.contact}－${row.nickname}`:row.nickname;}
function userAvatar(row){return /^data:image\/png;base64,/.test(row.avatar||'')?`<img class="user-avatar" src="${esc(row.avatar)}" alt="${esc(row.nickname)}的头像">`:'<span class="user-avatar user-avatar-empty" aria-label="未上传头像">人</span>';}
function userError(message){const box=$('#user-dialog-error');if(box)box.textContent=message;}
function closeUserDialog(){userAdmin.dialogEpoch++;$('#user-dialog')?.close();$('#user-dialog')?.remove();}
function openUserDialog(title,html){
  closeUserDialog();
  const dialog=document.createElement('dialog');dialog.id='user-dialog';dialog.className='user-dialog';
  dialog.innerHTML=`<div class="user-dialog-title"><h2>${esc(title)}</h2><button type="button" id="user-dialog-close" aria-label="关闭">关闭</button></div><p id="user-dialog-error" class="user-error" role="alert"></p><div id="user-dialog-content">${html}</div>`;
  document.body.appendChild(dialog);$('#user-dialog-close').onclick=closeUserDialog;
  dialog.addEventListener('cancel',event=>{event.preventDefault();closeUserDialog();});dialog.showModal();
  return userAdmin.dialogEpoch;
}
async function userSubmit(button,operation){
  button.disabled=true;userError('');
  try{await operation();}catch(error){userError(error.message);}finally{button.disabled=false;}
}
async function userReadAvatar(input){
  const file=input.files?.[0];
  if(!file)throw new Error('请选择头像图片');
  if(!['image/png','image/jpeg','image/webp'].includes(file.type)||file.size>512*1024)throw new Error('头像须为 PNG、JPEG 或 WebP，最大 512 KiB、400 万像素');
  return await new Promise((resolve,reject)=>{
    const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(new Error('头像读取失败'));reader.readAsDataURL(file);
  });
}
async function loadUsers(){
  const ticket=++userAdmin.request;
  const query=new URLSearchParams({query:userAdmin.query,contact:userAdmin.contact,offset:String(userAdmin.offset),limit:String(userAdmin.limit),channel_type:userAdmin.channel,status:userAdmin.status});
  try{
    const data=await userRequest('/api/users?'+query);
    if(ticket!==userAdmin.request||state.tab!=='users')return;
    userAdmin.rows=data.rows||[];userAdmin.total=data.total||0;userAdmin.error='';renderUsers();
  }catch(error){if(ticket===userAdmin.request&&state.tab==='users'){userAdmin.error=error.message;renderUsers();}}
}
function renderUsers(){
  const groups=new Map();for(const row of userAdmin.rows){if(!groups.has(row.user_id))groups.set(row.user_id,[]);groups.get(row.user_id).push(row);}
  $('#list').innerHTML=`<div class="user-filters"><h2>用户与记忆</h2><button id="user-create">新增用户</button><form id="user-filters"><label>会话名称<input name="contact" value="${esc(userAdmin.contact)}" placeholder="完整群名或私聊会话名"></label><label>会话类型<select name="channel"><option value="">全部</option><option value="group" ${userAdmin.channel==='group'?'selected':''}>群聊</option><option value="dm" ${userAdmin.channel==='dm'?'selected':''}>私聊</option></select></label><label>绑定状态<select name="status"><option value="">全部</option><option value="confirmed" ${userAdmin.status==='confirmed'?'selected':''}>已确认</option><option value="observed" ${userAdmin.status==='observed'?'selected':''}>待核对</option><option value="disabled" ${userAdmin.status==='disabled'?'selected':''}>已停用</option></select></label><button type="submit">应用筛选</button></form><p class="monitor-note">收到消息自动建立独立档案。长期记忆默认隔离，仅管理员手工关联后共享。</p></div>`;
  $('#pane').innerHTML=`<div class="head"><h2>用户与记忆</h2><p>共 ${userAdmin.total} 个绑定 · 固定 ID 不随昵称或头像改变</p></div>${userAdmin.error?`<p class="user-error" role="alert">${esc(userAdmin.error)}</p>`:''}<div class="monitor-table-wrap"><table class="monitor-table user-table"><thead><tr><th>头像</th><th>固定用户 ID</th><th>群名－昵称／私聊昵称</th><th>用户记忆</th></tr></thead><tbody>${userAdmin.rows.map(row=>`<tr><td>${userAvatar(row)}</td><td><code>${esc(row.user_id)}</code>${groups.get(row.user_id).length>1?`<details><summary>本页 ${groups.get(row.user_id).length} 个共享绑定</summary>${groups.get(row.user_id).map(other=>`<div>${esc(userLabel(other))}</div>`).join('')}</details>`:''}</td><td><strong>${esc(userLabel(row))}</strong><small>${row.channel_type==='group'?'群聊':'私聊 · '+esc(row.contact)} · ${userStatus(row)} · ${Number(row.avatar_count)||0} 个头像参考</small><button data-user-edit="${esc(row.binding_id)}">编辑绑定</button></td><td><button data-user-memory="${esc(row.binding_id)}">查看记忆（${Number(row.memory_count)||0}）</button></td></tr>`).join('')||'<tr><td colspan="4">暂无匹配用户。收到消息后自动建档，也可手动上传头像新增。</td></tr>'}</tbody></table></div><div class="pagination"><button id="user-prev" ${userAdmin.offset===0?'disabled':''}>上一页</button><span>${userAdmin.total?userAdmin.offset+1:0}–${Math.min(userAdmin.offset+userAdmin.limit,userAdmin.total)} / ${userAdmin.total}</span><button id="user-next" ${userAdmin.offset+userAdmin.limit>=userAdmin.total?'disabled':''}>下一页</button></div>`;
  $('#user-create').onclick=()=>editUserBinding();
  $('#user-filters').onsubmit=event=>{event.preventDefault();const form=event.currentTarget;userAdmin.contact=form.elements.contact.value.trim();userAdmin.channel=form.elements.channel.value;userAdmin.status=form.elements.status.value;userAdmin.offset=0;loadUsers();};
  $('#user-prev').onclick=()=>{userAdmin.offset=Math.max(0,userAdmin.offset-userAdmin.limit);loadUsers();};
  $('#user-next').onclick=()=>{userAdmin.offset+=userAdmin.limit;loadUsers();};
  document.querySelectorAll('[data-user-edit]').forEach(button=>button.onclick=()=>editUserBinding(userAdmin.rows.find(row=>row.binding_id===button.dataset.userEdit)));
  document.querySelectorAll('[data-user-memory]').forEach(button=>button.onclick=()=>loadUserMemory(button.dataset.userMemory));
}
function editUserBinding(row){
  const creating=!row;
  openUserDialog(creating?'新增用户':'编辑用户绑定',`<form id="user-binding-form" class="user-form">${creating?'<label>会话类型<select name="channel_type"><option value="group">群聊</option><option value="dm">私聊</option></select></label>':`<p>${userAvatar(row)} <code>${esc(row.user_id)}</code></p>`}<label>群名／私聊会话名<input name="contact" required maxlength="200" value="${esc(row?.contact||'')}"></label><label>群昵称／私聊昵称<input name="nickname" required maxlength="200" value="${esc(row?.nickname||'')}"></label>${creating?'':`<label class="user-check"><input type="checkbox" name="enabled" ${row.enabled?'checked':''}>启用此绑定</label>${row.status==='observed'?'<p class="user-warning">此记录尚待核对。确认身份后保存，才允许使用个人记忆。</p>':''}${row.observed_member_keys?.length?`<p class="monitor-note">已观测成员 ID：${row.observed_member_keys.map(esc).join(' / ')}</p>`:''}<label>人工确认的头像观测 ID（可选）<input name="member_key" maxlength="128" placeholder="仅填写已核对身份的历史 member_key"></label><p class="monitor-note">新增观测 ID 会成为该群身份的识别依据，请先核对工作流中的成员。原有参考保留。</p>`}<label>${creating?'头像截图':'补充头像参考（可选）'}<input name="avatar" type="file" accept="image/png,image/jpeg,image/webp" ${creating?'required':''}></label><p class="monitor-note">PNG / JPEG / WebP，最大 512 KiB、400 万像素；保存时移除元数据。创建后记忆从 0 条开始。</p><div class="row"><button type="submit">${creating?'创建用户':'保存绑定'}</button>${creating?'':'<button type="button" id="user-link">手工绑定为同一用户</button>'}</div></form>`);
  if(!creating)$('#user-link').onclick=()=>openUserLink(row);
  $('#user-binding-form').onsubmit=event=>{event.preventDefault();const form=event.currentTarget;const button=form.querySelector('[type=submit]');userSubmit(button,async()=>{
    const values={contact:form.elements.contact.value.trim(),nickname:form.elements.nickname.value.trim()};
    if(creating){values.channel_type=form.elements.channel_type.value;values.avatar=await userReadAvatar(form.elements.avatar);await userRequest('/api/users',{action:'create',...values});}
    else{
      const avatar=form.elements.avatar.files?.length?await userReadAvatar(form.elements.avatar):'';
      await userRequest('/api/users',{action:'update',binding_id:row.binding_id,version:row.version,...values,enabled:form.elements.enabled.checked,...(avatar?{avatar}:{}),...(form.elements.member_key.value.trim()?{member_key:form.elements.member_key.value.trim()}:{})});
    }
    closeUserDialog();loadUsers();
  });};
}
async function loadUserMemory(bindingId){
  const epoch=openUserDialog('用户记忆','<p>正在读取记忆…</p>');
  try{
    const result=await userRequest('/api/users/memory?'+new URLSearchParams({binding_id:bindingId}));
    if(epoch!==userAdmin.dialogEpoch)return;
    userAdmin.memory=result;userAdmin.memoryOffset=0;userAdmin.memoryQuery='';renderUserMemory();
  }catch(error){if(epoch===userAdmin.dialogEpoch)userError(error.message);}
}
function renderUserMemory(){
  const memory=userAdmin.memory,row=memory.binding;
  const items=memory.items.filter(item=>(item.key+' '+item.value).toLowerCase().includes(userAdmin.memoryQuery.toLowerCase()));
  const page=items.slice(userAdmin.memoryOffset,userAdmin.memoryOffset+20);
  $('#user-dialog-content').innerHTML=`<p><strong>${esc(userLabel(row))}</strong><br>用户 <code>${esc(row.user_id)}</code><br>绑定 <code>${esc(row.binding_id)}</code></p><p class="monitor-note">当前共享记忆范围：<code>${esc(row.memory_owner||row.user_id)}</code> · 版本 ${memory.version}。已关联的其他绑定也能使用这里的记忆。</p><div class="row"><button id="user-memory-add">新增记忆</button><button id="user-audit">修改记录</button><input id="user-memory-search" type="search" aria-label="搜索记忆" placeholder="搜索记忆" value="${esc(userAdmin.memoryQuery)}"></div><div class="monitor-table-wrap"><table class="monitor-table"><thead><tr><th>记忆 key</th><th>内容</th><th>更新</th><th>操作</th></tr></thead><tbody>${page.map((item,index)=>`<tr><td>${esc(item.key)}</td><td class="preview">${esc(item.value)}</td><td>${esc(full(item.updated))}</td><td><button data-memory-edit="${index}">修正</button><button data-memory-delete="${index}">删除</button></td></tr>`).join('')||'<tr><td colspan="4">此范围暂无匹配记忆。</td></tr>'}</tbody></table></div><div class="pagination"><button id="user-memory-prev" ${userAdmin.memoryOffset===0?'disabled':''}>上一页</button><span>${items.length?userAdmin.memoryOffset+1:0}–${Math.min(userAdmin.memoryOffset+20,items.length)} / ${items.length}</span><button id="user-memory-next" ${userAdmin.memoryOffset+20>=items.length?'disabled':''}>下一页</button></div>`;
  const workflowButton=document.createElement('button');workflowButton.type='button';workflowButton.textContent='查看此身份的工作流';
  workflowButton.onclick=()=>{closeUserDialog();state.viewSearch.workflow=row.binding_id;if(typeof workflow!=='undefined')workflow.scope='all';switchTab('workflow');};
  $('#user-memory-add').parentElement.appendChild(workflowButton);
  $('#user-memory-add').onclick=()=>editUserMemory();$('#user-audit').onclick=()=>{userAdmin.auditOffset=0;loadUserAudit();};
  $('#user-memory-search').onchange=event=>{userAdmin.memoryQuery=event.target.value;userAdmin.memoryOffset=0;renderUserMemory();};
  $('#user-memory-prev').onclick=()=>{userAdmin.memoryOffset-=20;renderUserMemory();};$('#user-memory-next').onclick=()=>{userAdmin.memoryOffset+=20;renderUserMemory();};
  document.querySelectorAll('[data-memory-edit]').forEach(button=>button.onclick=()=>editUserMemory(page[Number(button.dataset.memoryEdit)]));
  document.querySelectorAll('[data-memory-delete]').forEach(button=>button.onclick=()=>deleteUserMemory(page[Number(button.dataset.memoryDelete)]));
}
function editUserMemory(item){
  $('#user-dialog-content').innerHTML=`<form id="user-memory-form" class="user-form"><h3>${item?'修正记忆':'新增记忆'}</h3><label>记忆 key<input name="key" required maxlength="200" value="${esc(item?.key||'')}" ${item?'readonly':''}></label><label>内容<textarea name="value" required rows="6">${esc(item?.value||'')}</textarea></label><p class="monitor-note">保存后会更新共享范围，并使后续模型会话使用新的记忆版本。</p><div class="row"><button type="submit">保存记忆</button><button type="button" id="user-memory-back">返回</button></div></form>`;
  $('#user-memory-back').onclick=renderUserMemory;
  $('#user-memory-form').onsubmit=event=>{event.preventDefault();const form=event.currentTarget;userSubmit(form.querySelector('[type=submit]'),async()=>{
    await userRequest('/api/users',{action:'memory_set',binding_id:userAdmin.memory.binding.binding_id,version:userAdmin.memory.version,key:form.elements.key.value.trim(),value:form.elements.value.value});
    await loadUserMemory(userAdmin.memory.binding.binding_id);loadUsers();
  });};
}
function deleteUserMemory(item){
  $('#user-dialog-content').innerHTML=`<h3>删除记忆 ${esc(item.key)}</h3><p class="pre">${esc(item.value)}</p><p>该内容将从当前共享范围移除，后续模型不再召回。修改记录会保留。</p><div class="row"><button id="user-memory-delete-confirm">确认删除</button><button id="user-memory-back">返回</button></div>`;
  $('#user-memory-back').onclick=renderUserMemory;
  $('#user-memory-delete-confirm').onclick=event=>userSubmit(event.currentTarget,async()=>{
    await userRequest('/api/users',{action:'memory_delete',binding_id:userAdmin.memory.binding.binding_id,version:userAdmin.memory.version,key:item.key});
    await loadUserMemory(userAdmin.memory.binding.binding_id);loadUsers();
  });
}
async function loadUserAudit(){
  const epoch=userAdmin.dialogEpoch;
  try{
    const data=await userRequest('/api/users/audit?'+new URLSearchParams({binding_id:userAdmin.memory.binding.binding_id,offset:String(userAdmin.auditOffset),limit:'20'}));
    if(epoch!==userAdmin.dialogEpoch)return;
    $('#user-dialog-content').innerHTML=`<h3>修改记录 · ${esc(userLabel(userAdmin.memory.binding))}</h3><button id="user-memory-back">返回记忆</button><div class="monitor-table-wrap"><table class="monitor-table"><thead><tr><th>时间</th><th>操作</th><th>来源与内容</th></tr></thead><tbody>${data.rows.map(row=>`<tr><td>${esc(full(row.at))}</td><td>${esc(row.action)}</td><td class="preview"><pre>${esc(JSON.stringify(row.details,null,2))}</pre></td></tr>`).join('')||'<tr><td colspan="3">暂无修改记录。</td></tr>'}</tbody></table></div><div class="pagination"><button id="user-audit-prev" ${userAdmin.auditOffset===0?'disabled':''}>上一页</button><span>${userAdmin.auditOffset+data.rows.length} / ${data.total}</span><button id="user-audit-next" ${userAdmin.auditOffset+20>=data.total?'disabled':''}>下一页</button></div>`;
    $('#user-memory-back').onclick=renderUserMemory;$('#user-audit-prev').onclick=()=>{userAdmin.auditOffset-=20;loadUserAudit();};$('#user-audit-next').onclick=()=>{userAdmin.auditOffset+=20;loadUserAudit();};
  }catch(error){if(epoch===userAdmin.dialogEpoch)userError(error.message);}
}
function openUserLink(row){
  openUserDialog('手工绑定为同一用户',`<p>来源：${esc(userLabel(row))}<br><code>${esc(row.user_id)}</code></p><form id="user-link-find" class="user-form"><label>查找目标绑定<input name="query" placeholder="输入昵称、群名或固定 ID" required></label><button type="submit">查找</button></form><div id="user-link-targets"></div>`);
  $('#user-link-find').onsubmit=event=>{event.preventDefault();const form=event.currentTarget;userSubmit(form.querySelector('button'),async()=>{
    const epoch=userAdmin.dialogEpoch;const data=await userRequest('/api/users?'+new URLSearchParams({query:form.elements.query.value.trim(),limit:'50'}));
    if(epoch!==userAdmin.dialogEpoch)return;
    const targets=data.rows.filter(target=>target.binding_id!==row.binding_id&&target.user_id!==row.user_id);
    $('#user-link-targets').innerHTML=`<p class="monitor-note">匹配 ${data.total} 个绑定，最多显示 50 个；可用固定 ID 缩小范围。</p>${targets.map((target,index)=>`<p>${esc(userLabel(target))} · <code>${esc(target.user_id)}</code> <button data-link-target="${index}">预览共享范围</button></p>`).join('')||'<p>没有可关联的目标，请调整搜索。</p>'}`;
    document.querySelectorAll('[data-link-target]').forEach(button=>button.onclick=()=>previewUserLink(row,targets[Number(button.dataset.linkTarget)]));
  });};
}
async function userSharedBindings(userId,epoch){
  const rows=[];
  for(let offset=0;;offset+=100){
    const data=await userRequest('/api/users?'+new URLSearchParams({query:userId,offset:String(offset),limit:'100'}));
    if(epoch!==userAdmin.dialogEpoch)return [];
    rows.push(...data.rows.filter(row=>row.user_id===userId));
    if(offset+100>=data.total)return rows;
  }
}
function userLinkScope(left,right,bindings){
  const notes=(title,items)=>`<details><summary>${esc(title)} · ${items.length} 条</summary>${items.map(item=>`<p><strong>${esc(item.key)}</strong></p><pre class="pre">${esc(item.value)}</pre>`).join('')||'<p>暂无记忆。</p>'}</details>`;
  return `<h3>确认共享范围</h3><p>来源：${esc(userLabel(left.binding))}<br><code>${esc(left.binding.user_id)}</code> · ${left.items.length} 条记忆</p><p>目标：${esc(userLabel(right.binding))}<br><code>${esc(right.binding.user_id)}</code> · ${right.items.length} 条记忆</p><p>目标共享范围内的全部绑定：</p><ul class="user-link-scope">${bindings.map(row=>`<li>${esc(userLabel(row))}（${row.channel_type==='group'?'群聊':'私聊 · '+esc(row.contact)}${row.status==='disabled'?' · 已停用':''}）<br><code>${esc(row.binding_id)}</code></li>`).join('')}</ul>${notes('将合并的来源记忆',left.items)}${notes('目标已有记忆',right.items)}<p class="user-warning">关联后，来源绑定改用目标用户的共享记忆。群聊身份将能够使用目标范围内的私聊记忆；上述目标绑定也会读到合并内容。角色和聊天历史仍各自独立。</p>`;
}
async function previewUserLink(source,target){
  const epoch=userAdmin.dialogEpoch;
  try{
    const [left,right]=await Promise.all([source,target].map(row=>userRequest('/api/users/memory?'+new URLSearchParams({binding_id:row.binding_id}))));
    if(epoch!==userAdmin.dialogEpoch)return;
    const bindings=await userSharedBindings(right.binding.user_id,epoch);
    if(epoch!==userAdmin.dialogEpoch)return;
    const rightNotes=new Map(right.items.map(item=>[item.key,item.value]));
    const conflicts=left.items.filter(item=>rightNotes.has(item.key)&&rightNotes.get(item.key)!==item.value);
    $('#user-dialog-content').innerHTML=userLinkScope(left,right,bindings)+`<form id="user-link-confirm" class="user-form">${conflicts.map((item,index)=>`<fieldset><legend>同名 key：${esc(item.key)}</legend><div class="user-conflict"><label><input type="radio" name="conflict${index}" value="source" required>保留来源内容<pre>${esc(item.value)}</pre></label><label><input type="radio" name="conflict${index}" value="target" required>保留目标内容<pre>${esc(rightNotes.get(item.key))}</pre></label></div></fieldset>`).join('')||'<p>没有同名内容冲突，关联后合并两边记忆。</p>'}<label class="user-check"><input name="acknowledge" type="checkbox" required>我已核对两边身份，并同意上述记忆共享范围</label><button type="submit">确认共享记忆</button></form>`;
    $('#user-link-confirm').onsubmit=event=>{event.preventDefault();const form=event.currentTarget;userSubmit(form.querySelector('[type=submit]'),async()=>{
      const resolutions=Object.fromEntries(conflicts.map((item,index)=>[item.key,form.elements['conflict'+index].value]));
      const result=await userRequest('/api/users',{action:'link',binding_id:left.binding.binding_id,target_id:right.binding.binding_id,version:left.binding.version,resolutions,expected_versions:{source_memory:left.version,target_memory:right.version,target_binding:right.binding.version}});
      if(result.requires_confirmation)throw new Error('记忆内容已变化，请重新打开关联预览');
      closeUserDialog();loadUsers();
    });};
  }catch(error){if(epoch===userAdmin.dialogEpoch)userError(error.message);}
}
