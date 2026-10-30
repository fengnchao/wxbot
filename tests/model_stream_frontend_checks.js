const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const elements=new Map();
const element=s=>{if(!elements.has(s))elements.set(s,{innerHTML:'',textContent:'',scrollTop:0,classList:{toggle(){},remove(){}},querySelectorAll(){return []}});return elements.get(s)};
let pending=[],timerId=0;const timers=new Map();
const context=vm.createContext({FLOW_STAGE_LABELS:{},FLOW_STATUS_LABELS:{},state:{tab:'workflow'},
  document:{hidden:false,addEventListener(){},querySelectorAll(){return []}},
  $:element,currentQuery:()=>'',matchesQuery:()=>true,esc:s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
  hm:()=>'',full:()=>'',p2:String,groupFlowEvents:()=>[],markRefreshed(){},URLSearchParams,AbortController,
  setTimeout:f=>{timers.set(++timerId,f);return timerId},clearTimeout:id=>timers.delete(id),
  fetch:(url,options)=>new Promise(resolve=>pending.push({url,options,resolve}))});
vm.runInContext(fs.readFileSync('log/assets/workflow.js','utf8'),context);const run=s=>vm.runInContext(s,context);
const reply=(req,data,status=200)=>req.resolve({ok:status===200,json:async()=>data});
async function checks(){
  assert.match(run("workflowModelLabel({model:{label:'Hermes',model:'my-model'}})"),/Hermes.*my-model/);
  context.sample={model:{label:'DeepSeek',model:'selected',via_butler:false},messages:[],counts:{}};
  const diagram=run('workflowDiagram(sample,[],null,new Set())');
  assert.match(diagram,/DeepSeek/);assert.ok(!diagram.includes('id="wf-node-butler"'),'direct model does not invent Butler hop');
  run("workflow.overview=true;workflow.data={messages:[{id:'a',kind:'batch',terminal:false}]};renderWorkflow=()=>{}");
  const first=run('loadModelStream()');assert.equal(pending.length,1);const old=pending.shift();
  assert.match(old.url,/id=a/);
  run("workflow.selected='b';workflow.data.messages.push({id:'b',kind:'batch',terminal:false})");
  const second=run('loadModelStream()');assert.equal(old.options.signal.aborted,true);const latest=pending.shift();
  reply(latest,{id:'b',available:true,cursor:2,events:[{seq:1,type:'summary_delta',text:'<script>summary</script>'},{seq:2,type:'answer_delta',text:'answer',sendable:true}]});await second;
  reply(old,{id:'a',available:true,cursor:99,events:[{seq:99,type:'answer_delta',text:'stale'}]});await first;
  assert.equal(run('modelStream.id'),'b');assert.equal(run('modelStream.answer'),'answer');
  assert.match(run('workflowModelPanel()'),/&lt;script&gt;/);assert.ok(!run('workflowModelPanel()').includes('<script>'));
  const third=run('loadModelStream()'),leaving=pending.shift();run("stopWorkflow();state.tab='queue'");
  assert.equal(leaving.options.signal.aborted,true);
  reply(leaving,{id:'b',available:true,cursor:3,events:[{seq:3,type:'answer_delta',text:'late'}]});await third;
  assert.equal(run('modelStream.answer'),'');
  console.log('model stream frontend checks passed');
}checks().catch(e=>{console.error(e);process.exitCode=1});
