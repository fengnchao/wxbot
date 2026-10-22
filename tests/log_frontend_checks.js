const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const elements=new Map();
const decodeHtml=text=>String(text).replace(/&(amp|lt|gt|quot|#39);/g,(_,key)=>({amp:'&',lt:'<',gt:'>',quot:'"','#39':"'"}[key]));
function memoryElement(){
  let html='',nodes=new Map();
  return {textContent:'',value:'',disabled:false,dataset:{},classList:{toggle(){}},
    get innerHTML(){return html},set innerHTML(value){html=String(value);nodes.clear()},
    querySelectorAll(selector){
      const attribute=selector.match(/^\[([\w-]+)\]$/)?.[1];
      if(!attribute)return [];
      const matches=[];
      for(const match of html.matchAll(/<([a-z][\w-]*)\b([^>]*)>/g)){
        const attrs=Object.fromEntries(Array.from(match[2].matchAll(/([\w-]+)="([^"]*)"/g),a=>[a[1],decodeHtml(a[2])]));
        if(!(attribute in attrs))continue;
        if(!nodes.has(match.index)){
          const node=memoryElement(),body=html.slice(match.index+match[0].length).split(`</${match[1]}>`)[0];
          node.getAttribute=name=>attrs[name];
          node.dataset=Object.fromEntries(Object.entries(attrs).filter(([key])=>key.startsWith('data-')).map(([key,value])=>[key.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase()),value]));
          node.value=attrs.value??(match[1]==='textarea'?decodeHtml(body):match[1]==='select'?body.match(/<option value="([^"]*)"[^>]*selected/)?.[1]??body.match(/<option value="([^"]*)"/)?.[1]??'':'');
          node.disabled=/\bdisabled\b/.test(match[2]);
          nodes.set(match.index,node);
        }
        matches.push(nodes.get(match.index));
      }
      return matches;
    }
  };
}
function element(selector){
  if(!elements.has(selector)) elements.set(selector,memoryElement());
  return elements.get(selector);
}
let pending=[];
let accepted=true;
const confirmations=[];
const context=vm.createContext({
  document:{querySelector:element,querySelectorAll(){return []},addEventListener(){}},URLSearchParams,location:{search:''},
  setInterval(){return 1},clearInterval(){},confirm(message){confirmations.push(message);return accepted},
  localStorage:new Proxy({},{get(){throw new Error('configuration must not use localStorage')}}),
  fetch(url,options){return new Promise(resolve=>pending.push({url,options,resolve}));}
});
const html=fs.readFileSync('log/index.html','utf8');
const script=Array.from(html.matchAll(/<script src="\/assets\/([\w.-]+)"><\/script>/g),m=>fs.readFileSync('log/assets/'+m[1],'utf8')).join('\n').replace(/\nboot\(\);/,'\n');
vm.runInContext(script,context);
const run=source=>vm.runInContext(source,context);
const reply=(request,data,status=200)=>request.resolve({ok:status>=200&&status<300,status,json:async()=>JSON.parse(JSON.stringify(data))});
// A still-running old server serves the new HTML/app.js, but 404s new assets.
const missingWorkflowScript=Array.from(html.matchAll(/<script src="\/assets\/([\w.-]+)"><\/script>/g),m=>m[1])
  .filter(name=>name!=='workflow.js').map(name=>fs.readFileSync('log/assets/'+name,'utf8')).join('\n').replace(/\nboot\(\);/,'\n');
const missingWorkflowContext=vm.createContext({
  document:{querySelector:element,body:{classList:{toggle(){}}}},URLSearchParams,location:{search:''},
  setInterval(){return 1},clearInterval(){}
});
assert.doesNotThrow(()=>vm.runInContext(missingWorkflowScript,missingWorkflowContext),'missing optional workflow asset must not abort dashboard initialization');
vm.runInContext("switchTab('workflow');refreshCurrent();renderCurrentCached()",missingWorkflowContext);
assert.match(element('#pane').innerHTML,/重启.*log/);
vm.runInContext("loadQueue=()=>{state.queueLoaded=true};switchTab('queue')",missingWorkflowContext);
assert.equal(vm.runInContext('state.queueLoaded',missingWorkflowContext),true,'existing pages remain reachable without the workflow asset');
async function checks(){
  const topology=run("workflowDiagram({backend:'codex'},[],null,new Set())");
  assert.equal((topology.match(/data-service=\"butler\"/g)||[]).length,1,'one shared Butler for requests and replies');
  assert.equal((topology.match(/data-service=\"wxbot\"/g)||[]).length,1,'one shared wxbot');
  assert.equal((topology.match(/data-service=/g)||[]).length,5);
  assert.ok(topology.indexOf('data-service="model"')<topology.indexOf('data-service="butler"'));
  for(const edge of ['request','result','dispatch','enqueue','receive','send'])assert.match(topology,new RegExp('id="wf-edge-'+edge+'"'));
  assert.equal(run('workflowService(2)'),run('workflowService(4)'));
  assert.equal(run("workflowEventEdge({stage:'hermes_tool',status:'started'})"),'','tool progress must not pretend to be another model request');
  const hostile=run("workflowCard({id:'x\\\"<script>',uid:'u<&',contact:'<img src=x>',label:'A',members:[],group:false,inbox_ids:[1],request_id:'',kind:'inbox',message_count:1,stage:1,status:'unbatched',scope:'active',preview:'<script>alert(1)</script>',error:'',part_count:0,attempts:0},true)");
  assert.doesNotMatch(hostile,/<script>|<img src=x>/);
  assert.match(hostile,/&lt;script&gt;/);
  run("state.cdata={sections:[{rows:[{key:'butler.agent.provider',value:'codex'}]}]}");
  assert.equal(run("configurationCategory({id:'butler.codex',source_id:'butler'},{key:'butler.codex.model',path:['codex','model'],editable:true})"),'model');
  assert.equal(run("configurationCategory({id:'log',rows:[]},{key:'log.home',editable:false})"),'advanced');
  context.events=[{stage:'hermes_request',status:'started',ts:1},{stage:'hermes_request',status:'ok',ts:3}];
  assert.equal(run('groupFlowEvents(events).length'),1);
  assert.equal(run('groupFlowEvents(events)[0].elapsed_ms'),2000);
  context.toolEvents=[{stage:'hermes_tool',tool:'skills.read',status:'started',ts:1},
    {stage:'hermes_tool',tool:'skills.read',status:'failed',ts:2},
    {stage:'hermes_tool',tool:'memory.get',status:'started',ts:3},
    {stage:'hermes_tool',tool:'memory.get',status:'completed',ts:4},
    {stage:'hermes_tool',tool:'skills.read',status:'started',ts:5},
    {stage:'hermes_tool',tool:'skills.read',status:'completed',ts:6}];
  assert.equal(run('groupFlowEvents(toolEvents).length'),3,'tool occurrences without call IDs must remain separate');
  assert.equal(run('groupFlowEvents(toolEvents)[0].status'),'failed');
  context.completed={status:'ok',flows:[{id:'done1',contact:'A',state:'done',preview:'done',events:[]}]};
  assert.doesNotMatch(run('renderMessageFlow(completed)'),/class="flow-card[^>]*\sopen(?:\s|>)/);
  context.notStarted={status:'ok',flows:[{id:'pending1',contact:'A',state:'unbatched',preview:'pending',events:[
    {stage:'wxbot_received',status:'ok',ts:1},{stage:'wxbot_merge',status:'waiting',ts:null},
    {stage:'wechat_delivery',status:'not_started',ts:null}]}]};
  assert.equal(run("currentFlowStage(notStarted.flows[0].events)"),'wxbot_merge');
  // Simulate replacing DOM nodes during an automatic refresh.
  const originalPaneQuery=element('#pane').querySelectorAll;
  context.disclosures=[{dataset:{detail:'flow:stable'},open:true}];
  element('#pane').querySelectorAll=selector=>selector.startsWith('details')?context.disclosures:originalPaneQuery.call(element('#pane'),selector);
  element('#pane').dataset.view='wxbot';element('#pane').scrollTop=380;element('#list').scrollTop=120;
  run('rememberPane()');context.disclosures[0]={dataset:{detail:'flow:stable'},open:false};
  element('#pane').scrollTop=0;element('#list').scrollTop=0;run('restorePane()');
  assert.equal(context.disclosures[0].open,true);
  assert.equal(element('#pane').scrollTop,380);
  assert.equal(element('#list').scrollTop,120);
  context.disclosures[0].open=false;run('rememberPane()');context.disclosures[0]={dataset:{detail:'flow:stable'},open:true};run('restorePane()');
  assert.equal(context.disclosures[0].open,false,'a manually closed row must stay closed');
  element('#pane').querySelectorAll=originalPaneQuery;
  context.structured={key:'butler.contacts',label:'联系人',widget:'contacts'};
  const contactHtml=run("configurationStructuredControl(structured,JSON.stringify([{name:'A<script>',uid:'a',extra:'kept'}]),0,'<textarea></textarea>','')");
  assert.match(contactHtml,/data-c-contact/);assert.match(contactHtml,/A&lt;script&gt;/);assert.doesNotMatch(contactHtml,/<script>/);
  assert.match(run("configurationStructuredControl(structured,'[null]',0,'<textarea>fallback</textarea>','')"),/fallback/);
  const sentinel='<div>queue stays here</div>';
  element('#pane').innerHTML=sentinel;
  run("state.tab='wxbot'");
  const old=run('loadWxbot()');
  run("state.tab='queue'");
  reply(pending.shift(),{stats:{},contacts:[],events:[]});
  await old;
  assert.equal(element('#pane').innerHTML,sentinel,'an old tab response overwrote the queue tab');
  const base={read_only:true,status:'ok',at:1,database:'fake.db',contacts:[],counts:{unbatched:1},
    inbox:[],batches:[],outbox:[],pages:{inbox:{total:0},batches:{total:0},outbox:{total:0}}};
  const first=run('loadQueue()'), second=run('loadQueue()');
  const requests=pending.splice(0);
  reply(requests[1],{...base,database:'new.db'});
  await second;
  reply(requests[0],{...base,database:'old.db'});
  await first;
  assert.match(element('#pane').innerHTML,/new\.db/);
  assert.doesNotMatch(element('#pane').innerHTML,/old\.db/);
  context.fixture={...base,contacts:[{contact:'<script>bad</script>',unbatched:1,outbox:{},reason:{code:'blocked',message:'blocked',record_id:'id',error:'<img src=x onerror=bad>'}}],
    inbox:[{id:1,contact:'A',state:'unbatched',preview:'<script>bad</script>',characters:1,received_at:1}]};
  run("state.qdata=fixture;renderQueueNav();renderQueuePane()");
  assert.match(element('#pane').innerHTML,/&lt;script&gt;/);
  assert.doesNotMatch(element('#pane').innerHTML,/<script>/);
  assert.doesNotMatch(element('#list').innerHTML,/<script>/);
  context.fixture={...base,actions_enabled:true,events:[{at:1,contact:'A',action:'failed',reason:'<img src=x>',record_id:'task',source:'wxbot',details:{phase:'input_guard'}}],
    contacts:[{contact:'A',unbatched:1,outbox:{blocked:1},reason:{code:'blocked',state:'blocked',message:'failed',record_id:'task',record_kind:'outbox',finished_at:1,discard_at:181,actions:['retry','sent','skip']}}]};
  run('state.qdata=fixture;renderQueuePane()');
  assert.match(element('#pane').innerHTML,/人工核对/);
  assert.match(element('#pane').innerHTML,/data-q-action="retry"/);
  assert.match(element('#pane').innerHTML,/确认已发/);
  assert.match(element('#pane').innerHTML,/立即丢弃/);
  assert.match(element('#pane').innerHTML,/data-discard-at="181"/);
  assert.match(element('#pane').innerHTML,/&lt;img/);
  context.actionRows={...context.fixture,outbox:[{id:'task',contact:'A',state:'blocked',preview:'reply',actions:['retry','sent','skip']}]};
  run('state.qdata=actionRows;renderQueuePane()');
  assert.equal(element('#pane').querySelectorAll('[data-q-action]').length,3,'the same recovery actions must not appear twice');
  context.timeoutFixture={...base,failure_timeout_seconds:75,events:[{at:1,contact:'A',action:'timeout_discard',reason:'旧记录',record_id:'task'}]};
  run("state.qdata=timeoutFixture;renderQueuePane()");
  assert.match(element('#pane').innerHTML,/最多等待75秒/,'queue help must use the configured timeout');
  assert.match(element('#pane').innerHTML,/失败超时丢弃/,'historical discard events must not claim the current timeout');
  assert.match(element('#pane').innerHTML,/运行参数未核验/);
  assert.doesNotMatch(element('#pane').innerHTML,/3分钟/);
  run("delete state.qdata.failure_timeout_seconds;renderQueuePane()");
  assert.match(element('#pane').innerHTML,/最多等待180秒/,'old queue payloads must keep the 180-second default');
  accepted=false;
  await run("performQueueAction({id:'fake',kind:'outbox',contact:'A'},'retry')");
  assert.match(confirmations.at(-1),/首次失败的超时期限不会重置/);
  accepted=true;
  context.snapshot={id:'task',kind:'outbox',contact:'A',expected_state:'blocked',expected_finished_at:1};
  run("state.qBusy=false;state.tab='queue'");
  const operation=run("performQueueAction(snapshot,'skip')");
  const mutation=pending.shift();
  assert.equal(mutation.url,'/api/queue-action');
  assert.equal(mutation.options.headers['X-Wxbot-Queue-Action'],'1');
  assert.equal(JSON.parse(mutation.options.body).id,'task');
  assert.equal(JSON.parse(mutation.options.body).acknowledge,true);
  run("state.tab='configuration'");
  reply(mutation,{ok:true});
  await operation;
  context.config={note:'file configuration only',sources:[],sections:[{id:'queue',title:'queue',source:'fake.toml',
    rows:[{key:'wxbot.queue.quiet_seconds',value:3,origin:'default'},{key:'wxbot.custom.note',value:'<script>bad</script>',origin:'file'}]}]};
  run("state.tab='configuration';state.cSection='all';state.cdata=config;renderConfigurationNav();renderConfigurationPane()");
  assert.match(element('#pane').innerHTML,/quiet_seconds/);
  assert.doesNotMatch(element('#pane').innerHTML,/<script>/);
  run("state.cSearch='quiet_seconds';renderConfigurationPane()");
  assert.match(element('#pane').innerHTML,/quiet_seconds/);
  assert.doesNotMatch(element('#pane').innerHTML,/custom\.note/);
  assert.equal(typeof element('#tab-queue').onclick,'function');
  assert.equal(typeof element('#tab-configuration').onclick,'function');
  await configurationEditorChecks();
  context.flow={read_only:true,status:'ok',at:1,total:1,offset:0,has_more:false,sources:[],
    flows:[{id:'inbox:1',request_id:'',contact:'A<script>bad</script>',preview:'new message',state:'unbatched',
      at:1,message_count:1,inbox_ids:[1],reason:{code:'blocked',message:'old delivery blocked',record_id:'old-id',error:'<img src=x onerror=bad>'},
      events:[{stage:'wxbot_received',status:'ok',ts:1},{stage:'wxbot_merge',status:'blocked',ts:null,blocker_id:'old-id'},
        {stage:'hermes_tool',status:'running',ts:2,tool:'skill_view',tool_call_id:'tool-1'},
        {stage:'butler_received',status:'not_started',ts:null}]}]};
  const flowHtml=run("state.wUid='all';renderMessageFlow(flow)");
  assert.match(flowHtml,/new message/);
  assert.match(flowHtml,/old-id/);
  assert.match(flowHtml,/skill_view/);
  assert.match(flowHtml,/未提交/);
  assert.match(flowHtml,/&lt;script&gt;/);
  assert.doesNotMatch(flowHtml,/<script>|<img/);
  console.log('frontend checks passed');
}
async function configurationEditorChecks(){
  // These checks catch lost drafts, stale versions, accidental secret writes, and unconfirmed mutations.
  context.editorConfig={note:'<img src=x onerror=bad>',warnings:['<script>bad</script>'],sources:[
    {id:'wxbot',title:'微信配置',path:'fake.toml',status:'ok',version:'wx-v1'},
    {id:'butler',title:'Butler 配置',path:'fake.json',status:'ok',version:'butler-v1'},
    {id:'broken',title:'错误来源',path:'broken.json',status:'error',version:'broken-v1',error:'<img src=x>'},
    {id:'new-log-config',title:'日志服务配置',path:'not-yet-created.json',status:'missing',version:'missing-v1'}
  ],sections:[
    {id:'queue',title:'队列参数',source_id:'wxbot',source:'fake.toml',rows:[
      {key:'wxbot.enabled',path:['wxbot','enabled'],value:true,origin:'file',editable:true,editor:'boolean',label:'启用机器人',description:'控制消息处理',effect:'重启 wxbot 后生效',default_available:true},
      {key:'wxbot.timeout',path:['wxbot','timeout'],value:10,origin:'default',editable:true,editor:'integer',label:'超时时间',description:'等待服务响应的秒数',effect:'重启 wxbot 后生效'},
      {key:'wxbot.filters',path:['wxbot','filters'],value:['A'],origin:'file',editable:true,editor:'json',label:'过滤列表',description:'JSON 列表',effect:'重启 wxbot 后生效'},
      {key:'wxbot.api_key',path:['wxbot','api_key'],value:'已配置（已隐藏）',origin:'file',editable:true,editor:'secret',sensitive:true,label:'连接密钥',description:'服务凭据',effect:'重启 wxbot 后生效'},
      {key:'runtime.pid',path:['pid'],value:123,origin:'runtime',editable:false,label:'运行进程'},
      {key:'legacy.option',value:'legacy',origin:'file'}]},
    {id:'custom',title:'自定义参数',source_id:'wxbot',source:'fake.toml',rows:[
      {key:'custom.key',path:['custom.key'],value:'old',origin:'file',editable:true,editor:'string',label:'自定义文本 <img src=x>',description:'保留带点的原始键',effect:'重启 wxbot 后生效'}]},
    {id:'hermes',title:'模型连接',source_id:'butler',source:'fake.json',rows:[
      {key:'hermes.url',path:['hermes','url'],value:'http://example.invalid',origin:'file',editable:true,editor:'string',label:'模型服务地址',description:'Hermes 连接 URL',effect:'重启 Butler 后生效'}]},
    {id:'broken',title:'不可读取',source_id:'broken',source:'broken.json',rows:[
      {key:'broken.enabled',path:['enabled'],value:false,editable:true,editor:'boolean',label:'不可保存'}]},
    {id:'log-config',title:'日志服务',source_id:'new-log-config',source:'not-yet-created.json',rows:[
      {key:'port',path:['port'],value:8800,origin:'default',editable:true,editor:'integer',label:'日志端口',description:'日志服务监听端口',effect:'重启 log 后生效；命令行端口优先'}]}
  ]};
  run("state.tab='configuration';state.cSearch='';state.cSection='all';state.cdata=editorConfig;renderConfigurationPane()");
  assert.match(element('#pane').innerHTML,/保存此文件/,'configuration sources must expose editable save controls');
  assert.match(element('#pane').innerHTML,/控制消息处理/);
  assert.match(element('#pane').innerHTML,/重启 wxbot 后生效/);
  assert.match(element('#pane').innerHTML,/type="number"/);
  assert.match(element('#pane').innerHTML,/type="password"/);
  assert.match(element('#pane').innerHTML,/恢复默认/);
  assert.doesNotMatch(element('#pane').innerHTML,/<script>|<img/);
  const controls=element('#pane').querySelectorAll('[data-c-editor]');
  assert.equal(controls.length,7,'missing files with a version must be editable; runtime facts and error sources stay read only');
  assert.match(element('#pane').innerHTML,/环境变量/);
  assert.match(element('#pane').innerHTML,/命令行/);
  assert.equal(controls.find(el=>el.getAttribute('aria-label')==='连接密钥').value,'','the masked status is never a secret input value');
  assert.equal(controls.find(el=>el.getAttribute('aria-label')==='连接密钥').disabled,true);
  assert.equal(element('#pane').querySelectorAll('[data-c-default]').length,1,'only available defaults may offer a reset');
  run("state.cSearch='Hermes 连接';renderConfigurationPane()");
  assert.match(element('#pane').innerHTML,/hermes\.url/,'Chinese purpose text must be searchable');
  assert.doesNotMatch(element('#pane').innerHTML,/legacy\.option/);
  run("state.cSearch='';setConfigurationDraft('wxbot',editorConfig.sections[0].rows[0],'false');setConfigurationDraft('wxbot',editorConfig.sections[0].rows[1],'23');setConfigurationDraft('wxbot',editorConfig.sections[1].rows[0],'<textarea>new</textarea>');setConfigurationDraft('wxbot',editorConfig.sections[0].rows[3],'','keep')");
  const before=pending.length;
  await run('loadConfiguration()');
  assert.equal(pending.length,before,'automatic refresh must preserve drafts without replacing the form');
  run("state.cSection='custom';renderConfigurationPane();state.cSection='all';renderConfigurationPane()");
  assert.match(element('#pane').innerHTML,/&lt;textarea&gt;new&lt;\/textarea&gt;/);
  assert.doesNotMatch(element('#pane').innerHTML,/<textarea>new/);
  accepted=false;
  await run("saveConfigurationSource('wxbot')");
  assert.equal(pending.length,before,'declined confirmation must never POST');
  accepted=true;
  const saving=run("saveConfigurationSource('wxbot')");
  const request=pending.shift();
  assert.equal(request.url,'/api/configuration');
  assert.equal(request.options.method,'POST');
  assert.equal(request.options.headers['X-Wxbot-Config-Action'],'1');
  assert.equal(request.options.headers['Content-Type'],'application/json');
  assert.deepEqual(JSON.parse(request.options.body),{source:'wxbot',version:'wx-v1',acknowledge:true,changes:[
    {path:['wxbot','enabled'],op:'set',value:false},
    {path:['wxbot','timeout'],op:'set',value:23},
    {path:['custom.key'],op:'set',value:'<textarea>new</textarea>'}
  ]},'one file must combine sections and preserve true key paths and input types');
  assert.match(confirmations.at(-1),/启用机器人/);
  assert.match(confirmations.at(-1),/wxbot/);
  assert.doesNotMatch(confirmations.at(-1),/已配置（已隐藏）/);
  run("state.tab='queue'");
  element('#pane').innerHTML='queue remains selected';
  reply(request,{ok:true,message:'已保存',restart:['wxbot'],backup:'safe.backup'});
  await saving;
  assert.equal(element('#pane').innerHTML,'queue remains selected','save completion must not repaint a different tab');
  assert.equal(pending.length,0,'save completion on a different tab must wait before reloading configuration');
  run("state.tab='configuration';state.cRefreshNeeded=false;setConfigurationDraft('wxbot',editorConfig.sections[0].rows[2],'{invalid')");
  await run("saveConfigurationSource('wxbot')");
  assert.equal(pending.length,0,'invalid JSON must never POST');
  assert.match(element('#pane').innerHTML,/JSON/);
  run("cancelConfigurationSource('wxbot');setConfigurationDraft('wxbot',editorConfig.sections[0].rows[1],'2.5')");
  await run("saveConfigurationSource('wxbot')");
  assert.equal(pending.length,0,'fractional integer values must never POST');
  run("cancelConfigurationSource('wxbot');setConfigurationDraft('wxbot',editorConfig.sections[0].rows[3],'new-secret-<private>','set');renderConfigurationPane()");
  assert.doesNotMatch(element('#pane').innerHTML,/new-secret|<private>/,'secret drafts must never be interpolated into HTML');
  const replacing=run("saveConfigurationSource('wxbot')");
  const secretRequest=pending.shift();
  await run("saveConfigurationSource('wxbot')");
  assert.equal(pending.length,0,'an in-flight save must block duplicate submissions');
  assert.deepEqual(JSON.parse(secretRequest.options.body).changes,[{path:['wxbot','api_key'],op:'set',value:'new-secret-<private>'}]);
  assert.doesNotMatch(confirmations.at(-1),/new-secret/,'confirmation must exclude secret input');
  reply(secretRequest,{ok:false,error:'文件已变化 <script>bad</script>'},409);
  await replacing;
  assert.match(element('#pane').innerHTML,/刷新/);
  assert.match(element('#pane').innerHTML,/&lt;script&gt;/);
  assert.doesNotMatch(element('#pane').innerHTML,/<script>|new-secret/);
  assert.equal(run("state.cDrafts.get('wxbot').changes.size"),1,'version conflicts must retain the draft');
  run("cancelConfigurationSource('wxbot');setConfigurationDraft('wxbot',editorConfig.sections[0].rows[3],'','set')");
  await run("saveConfigurationSource('wxbot')");
  assert.equal(pending.length,0,'an empty secret replacement must never become a stored placeholder');
  run("cancelConfigurationSource('wxbot');setConfigurationDraft('wxbot',editorConfig.sections[0].rows[3],'','clear');setConfigurationDraft('wxbot',editorConfig.sections[0].rows[0],'','default')");
  const clearing=run("saveConfigurationSource('wxbot')");
  const clearRequest=pending.shift();
  assert.deepEqual(JSON.parse(clearRequest.options.body).changes,[{path:['wxbot','api_key'],op:'clear'},{path:['wxbot','enabled'],op:'default'}]);
  run("state.tab='queue'");
  reply(clearRequest,{ok:true,message:'已保存',restart:['wxbot']});
  await clearing;
  run("state.tab='configuration';state.cRefreshNeeded=false;setConfigurationDraft('broken',editorConfig.sections[3].rows[0],'true');setConfigurationDraft('wxbot',editorConfig.sections[0].rows[4],'456');setConfigurationDraft('wxbot',editorConfig.sections[0].rows[1],'','default')");
  await run("saveConfigurationSource('broken');saveConfigurationSource('wxbot')");
  assert.equal(pending.length,0,'error sources, runtime facts, and unavailable defaults must not save');
  const stale=run('loadConfiguration()');
  const staleRequest=pending.shift();
  run("setConfigurationDraft('butler',editorConfig.sections[2].rows[0],'http://draft.invalid');state.cSection='hermes';renderConfigurationPane()");
  reply(staleRequest,{...context.editorConfig,sections:[]});
  await stale;
  assert.match(element('#pane').innerHTML,/http:\/\/draft\.invalid/,'an in-flight refresh must not overwrite a new draft');
  run("cancelConfigurationSource('butler');state.cSection='all';state.cRefreshNeeded=false");
  const first=run('loadConfiguration()'),second=run('loadConfiguration()');
  const reads=pending.splice(0);
  reply(reads[1],{...context.editorConfig,note:'latest configuration'});await second;
  reply(reads[0],{...context.editorConfig,note:'old configuration'});await first;
  assert.match(element('#pane').innerHTML,/latest configuration/);
  assert.doesNotMatch(element('#pane').innerHTML,/old configuration/);
  const leaving=run('loadConfiguration()'),lateRead=pending.shift();
  run("state.tab='queue'");element('#pane').innerHTML='another tab is active';
  reply(lateRead,context.editorConfig);await leaving;
  assert.equal(element('#pane').innerHTML,'another tab is active','configuration reads must not repaint a different tab');
  run("state.tab='configuration'");
  await configurationControlChecks();
  await configurationSourceVisibilityChecks();
}
async function configurationControlChecks(){
  run("state.cdata=editorConfig;state.cSearch='';state.cSection='all';state.cRefreshNeeded=false;renderConfigurationPane()");
  const input=label=>element('#pane').querySelectorAll('[data-c-editor]').find(el=>el.getAttribute('aria-label')===label);
  const secretMode=()=>element('#pane').querySelectorAll('[data-c-secret]')[0];
  secretMode().value='set';secretMode().onchange();
  assert.equal(input('连接密钥').disabled,false,'choosing replace must enable the secret field');
  input('连接密钥').value='secret-event-value';input('连接密钥').oninput();
  run("state.cSection='hermes';renderConfigurationPane();state.cSection='all';renderConfigurationPane()");
  assert.equal(input('连接密钥').value,'secret-event-value','category changes must restore secrets through the input property');
  assert.doesNotMatch(element('#pane').innerHTML,/secret-event-value/);
  secretMode().value='keep';secretMode().onchange();
  assert.equal(input('连接密钥').value,'');
  assert.equal(run('state.cDrafts.size'),0,'choosing keep must remove the replacement draft');
  input('超时时间').value='42';input('超时时间').oninput();
  const wxSave=element('#pane').querySelectorAll('[data-c-save]')[0];
  assert.equal(wxSave.disabled,false,'editing a field must enable its source save button');
  assert.equal(element('#pane').querySelectorAll('[data-c-save]')[1].disabled,true,'unmodified sources must stay disabled');
  input('模型服务地址').value='http://draft.invalid';input('模型服务地址').oninput();
  const saved=wxSave.onclick(),post=pending.shift();
  reply(post,{ok:true,message:'已保存',restart:['wxbot']});
  await new Promise(setImmediate);
  const reload=pending.shift();
  assert.equal(reload.url,'/api/configuration');
  const changed=JSON.parse(JSON.stringify(context.editorConfig));
  changed.sources[0].version='wx-v2';changed.sources[1].version='butler-v2';
  changed.sections[0].rows[1].value=42;changed.sections[2].rows[0].value='http://external.invalid';
  reply(reload,changed);await saved;
  assert.equal(input('超时时间').value,'42');
  assert.match(element('#pane').innerHTML,/需重启：wxbot/,'successful saves must explain which service needs a restart');
  assert.equal(input('模型服务地址').value,'http://draft.invalid','saving a different file must preserve unsaved inputs');
  const butlerSave=run("saveConfigurationSource('butler')"),butlerPost=pending.shift();
  assert.equal(JSON.parse(butlerPost.options.body).version,'butler-v1','refresh must retain the version that a draft was based on');
  reply(butlerPost,{ok:false,error:'暂时无法保存'},503);await butlerSave;
  assert.match(element('#pane').innerHTML,/暂时无法保存/);
  assert.equal(input('模型服务地址').value,'http://draft.invalid','save errors must preserve inputs');
  accepted=false;
  await element('#c-reload').onclick();
  assert.equal(pending.length,0,'declining reload must keep all drafts');
  assert.equal(input('模型服务地址').value,'http://draft.invalid');
  accepted=true;
  const refreshing=element('#c-reload').onclick(),read=pending.shift();
  reply(read,changed);await refreshing;
  assert.equal(input('模型服务地址').value,'http://external.invalid');
  assert.equal(run('state.cDrafts.size'),0,'confirmed reload must release secret and ordinary drafts');
  const defaults=element('#pane').querySelectorAll('[data-c-default]');
  defaults[0].onclick();
  assert.match(element('#pane').innerHTML,/待保存：恢复默认值/);
  run("cancelConfigurationSource('wxbot')");
  assert.doesNotMatch(element('#pane').innerHTML,/待保存：恢复默认值/);
  input('日志端口').value='8801';input('日志端口').oninput();
  const creating=run("saveConfigurationSource('new-log-config')"),newFile=pending.shift();
  assert.deepEqual(JSON.parse(newFile.options.body),{source:'new-log-config',version:'missing-v1',changes:[{path:['port'],op:'set',value:8801}],acknowledge:true},'missing sources with a version must be creatable');
  run("state.tab='queue'");
  reply(newFile,{ok:true,message:'已创建',restart:['log']});await creating;
}
async function configurationSourceVisibilityChecks(){
  run("state.tab='configuration';state.cdata=editorConfig;state.cDrafts.clear();state.cMessages.clear();state.cRefreshNeeded=false;state.cSearch='';state.cSection='hermes';renderConfigurationPane()");
  const sourceButtons=()=>element('#pane').querySelectorAll('[data-c-save]');
  assert.deepEqual(sourceButtons().map(button=>button.dataset.cSave),['1','2'],'a single section must hide unrelated healthy sources while retaining source errors and original indices');
  assert.doesNotMatch(element('#pane').innerHTML,/not-yet-created\.json|微信配置/);
  assert.match(element('#pane').innerHTML,/hermes\.url/);
  run("setConfigurationDraft('new-log-config',editorConfig.sections[4].rows[0],'8802');renderConfigurationPane()");
  assert.deepEqual(sourceButtons().map(button=>button.dataset.cSave),['1','2','3'],'drafts from another section must keep their source save area visible');
  const logSave=sourceButtons().find(button=>button.dataset.cSave==='3');
  assert.equal(logSave.disabled,false);
  const saving=logSave.onclick(),post=pending.shift();
  assert.deepEqual(JSON.parse(post.options.body),{source:'new-log-config',version:'missing-v1',changes:[{path:['port'],op:'set',value:8802}],acknowledge:true},'a filtered save button must still target its original source');
  reply(post,{ok:false,error:'跨分类保存错误'},503);await saving;
  assert.match(element('#pane').innerHTML,/跨分类保存错误/);
  run("state.cDrafts.delete('new-log-config');renderConfigurationPane()");
  assert.deepEqual(sourceButtons().map(button=>button.dataset.cSave),['1','2','3'],'source error messages must remain visible even without drafts');
  run("state.cMessages.delete('new-log-config');state.cMessages.set('wxbot',{text:'已保存，需重启 wxbot'});renderConfigurationPane()");
  assert.deepEqual(sourceButtons().map(button=>button.dataset.cSave),['0','1','2'],'successful saves from another section must retain their feedback');
  assert.match(element('#pane').innerHTML,/已保存，需重启 wxbot/);
  run("state.cMessages.clear();state.cSearch='no matching configuration';renderConfigurationPane()");
  assert.deepEqual(sourceButtons().map(button=>button.dataset.cSave),['2'],'search-hidden sections must not reserve healthy source save areas');
  run("state.cSearch='';state.cSection='all';renderConfigurationPane()");
}
checks().catch(error=>{console.error(error);process.exitCode=1});
