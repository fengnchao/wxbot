const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const elements=new Map();
function element(selector){
  if(!elements.has(selector)) elements.set(selector,{
    innerHTML:'',textContent:'',value:'',classList:{toggle(){}},querySelectorAll(){return []}
  });
  return elements.get(selector);
}
let pending=[];
const context=vm.createContext({
  document:{querySelector:element},URLSearchParams,location:{search:''},
  setInterval(){return 1},clearInterval(){},confirm(){return true},
  fetch(url,options){return new Promise(resolve=>pending.push({url,options,resolve}));}
});
const html=fs.readFileSync('log/index.html','utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1].replace(/\nboot\(\);/,'\n');
vm.runInContext(script,context);
const run=source=>vm.runInContext(source,context);
const reply=(request,data)=>request.resolve({ok:true,json:async()=>data});
async function checks(){
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
  run("state.tab='configuration';state.cdata=config;renderConfigurationNav();renderConfigurationPane()");
  assert.match(element('#pane').innerHTML,/quiet_seconds/);
  assert.doesNotMatch(element('#pane').innerHTML,/<script>/);
  run("state.cSearch='quiet_seconds';renderConfigurationPane()");
  assert.match(element('#pane').innerHTML,/quiet_seconds/);
  assert.doesNotMatch(element('#pane').innerHTML,/custom\.note/);
  assert.equal(typeof element('#tab-queue').onclick,'function');
  assert.equal(typeof element('#tab-configuration').onclick,'function');
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
checks().catch(error=>{console.error(error);process.exitCode=1});
