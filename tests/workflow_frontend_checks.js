/* Lifecycle checks with a fake browser and deferred HTTP; no real server or clipboard. */
const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
const elements=new Map(),requests=[],timers=new Map();let timerId=0,renders=0,pulses=0;
function el(key){if(!elements.has(key))elements.set(key,{textContent:'',dataset:{},classList:{toggle(){},remove(){},add(){}},querySelectorAll(){return []}});return elements.get(key);}
const sandbox={document:{querySelector:el,querySelectorAll(){return []},addEventListener(){},hidden:false},
  AbortController,Date,console, state:{tab:'workflow'},matchesQuery(){return true},
  setTimeout(fn,ms){timers.set(++timerId,{fn,ms});return timerId},clearTimeout(id){timers.delete(id)},
  markRefreshed(){},fetch(url,opts){return new Promise((resolve,reject)=>requests.push({url,opts,resolve,reject}))},
  esc:String,$:el};
const context=vm.createContext(sandbox),run=s=>vm.runInContext(s,context);
vm.runInContext(fs.readFileSync('log/assets/workflow.js','utf8'),context);
context.rendered=()=>renders++;context.pulsed=events=>pulses+=events.length;
run('renderWorkflow=rendered;pulseWorkflow=pulsed');
const event=(key,ts,node=1)=>({key,ts,node,stage:'wxbot_merge',status:'ok'});
const message=(id,events)=>({id,uid:'uid-a',contact:'A',members:[],inbox_ids:[1],events});
const snapshot=(at,messages)=>({at,messages,status:'ok',counts:{},sources:[]});
async function response(request,data){request.resolve({ok:true,json:async()=>data});await new Promise(setImmediate);}
async function main(){
  context.old=snapshot(10,[message('inbox:1',[event('received',1)])]);
  context.next=snapshot(11,[message('batch1',[event('received',1),event('merge',10.5)])]);
  assert.equal(run('workflowFresh(old,next,false).length'),0,'initial history must not animate');
  assert.equal(run('workflowFresh(old,next,true).length'),1,'only a new event animates after merge');
  assert.equal(run('workflowFresh(next,next,true).length'),0,'unchanged snapshots must stay still');
  context.queued=snapshot(20,[{...message('b',[event('pending',4,5)]),stage:5,status:'pending',delivery_id:'d1'}]);
  context.typing=snapshot(21,[{...message('b',[event('sending',4,6)]),stage:6,status:'sending',delivery_id:'d1'}]);
  assert.equal(run('workflowFresh(queued,typing,true).length'),1,'observed queue transition must animate even without a stored start timestamp');
  assert.equal(run('workflowColor(old.messages[0])===workflowColor(next.messages[0])'),true);
  run('loadWorkflow();loadWorkflow()');assert.equal(requests.length,1,'one in-flight fetch');
  await response(requests.shift(),context.old);assert.equal(pulses,0);
  run("workflow.selected='inbox:1';loadWorkflow()");await response(requests.shift(),context.next);
  assert.equal(run('workflow.selected'),'batch1','selection follows inbox → batch lineage');assert.equal(pulses,1);
  run('workflow.paused=true;loadWorkflow()');await response(requests.shift(),snapshot(12,[message('batch1',[event('tool',12,3)])]));
  assert.equal(pulses,1,'paused animations keep fetching without movement');
  run('loadWorkflow()');requests.shift().reject(new Error('offline'));await new Promise(setImmediate);
  assert.equal(run('workflow.baseline'),false);assert.equal(run('workflow.data.at'),12,'preserve last snapshot on disconnect');
  run('workflow.paused=false;loadWorkflow()');await response(requests.shift(),snapshot(20,[message('batch1',[event('done',19,7)])]));
  assert.equal(pulses,1,'reconnect must not replay missed history as live movement');
  run('loadWorkflow()');requests.shift().resolve({ok:false,status:404});await new Promise(setImmediate);
  assert.match(run('workflow.error'),/重启 log/,'an old server must explain the required restart');
  run('loadWorkflow();stopWorkflow();state.tab="queue"');const abandoned=requests.shift();assert.equal(abandoned.opts.signal.aborted,true);
  const count=renders;await response(abandoned,snapshot(21,[]));assert.equal(renders,count,'late response cannot overwrite another page');
  console.log('workflow frontend checks passed');
}
main().catch(e=>{console.error(e);process.exitCode=1});
