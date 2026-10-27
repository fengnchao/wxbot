"""Offline browser-model checks for relay settings drafts and escaping."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_relay_admin_frontend_preserves_pending_changes():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js needed for dashboard checks')
    root = Path(__file__).resolve().parents[1]
    script = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const elements=new Map();
function element(selector){
  if(!elements.has(selector))elements.set(selector,{innerHTML:'',value:'',dataset:{},querySelectorAll(){return []}});
  return elements.get(selector);
}
let pending=[];
const context=vm.createContext({
  $:element,state:{tab:'telegram-relay'},full:v=>String(v),
  esc:v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
  get:async()=>context.incoming,
  fetch:(url,options)=>new Promise(resolve=>pending.push({url,options,resolve}))
});
vm.runInContext(fs.readFileSync('log/assets/telegram_relay.js','utf8'),context);
const run=source=>vm.runInContext(source,context);
context.incoming={settings:{enabled:false,include_text:true,include_images:false,include_source:true,include_time:true,
  window_title:'Telegram',bot_username:'',bot_id:0,poll_interval:5,album_quiet_seconds:2,max_album_wait:15,
  admin_contacts:[],channels:[{key:'news',name:'<img src=x>',username:'daily_news',chat_id:0,enabled:false}],desktop:{}},
  version:'v1',runtime:{state:'unavailable'},note:'<script>hostile</script>'};
async function checks(){
  await run('loadTelegramRelay()');
  assert.match(element('#pane').innerHTML,/&lt;img src=x&gt;/);
  assert.doesNotMatch(element('#pane').innerHTML,/<script>|<img src=x>/);
  run("relayDraft().window_title='My Telegram'");
  context.incoming={...context.incoming,version:'v2'};
  await run('loadTelegramRelay()');
  assert.equal(run('relayAdmin.version'),'v1','refresh retains draft original version');
  assert.equal(run('relayAdmin.draft.window_title'),'My Telegram');
  const saving=run('saveTelegramRelay()');
  const request=pending.pop();
  assert.equal(request.url,'/api/telegram-relay');
  assert.equal(request.options.headers['X-Wxbot-Relay-Action'],'1');
  assert.equal(JSON.parse(request.options.body).version,'v1');
  request.resolve({ok:false,json:async()=>({error:'changed; refresh'})});
  await saving;
  assert.equal(run('relayAdmin.draft.window_title'),'My Telegram','stale save preserves draft');
  assert.match(run('relayAdmin.error'),/changed/);
  assert.equal(run('relayAdmin.busy'),false);
  run("relayAdmin.desktopText='invalid json'");
  await run('saveTelegramRelay()');
  assert.equal(pending.length,0,'invalid selector JSON does not write');
  assert.equal(run('relayAdmin.draft.window_title'),'My Telegram');
  const review=run("relayReviewTasks({ui_hold:true,tasks:[{id:'desktop',channel:'news',state:'blocked',error:'<unsafe>'},{id:'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',channel:'news',state:'uncertain',source_id:'123',submitted:1}]},relayAdmin.data.settings)");
  assert.match(review,/先.*清理.*Telegram/);
  assert.match(review,/频道键.*news/);
  assert.match(review,/消息 ID.*123/);
  assert.doesNotMatch(review,/<unsafe>/);
  assert.doesNotMatch(review,/data-relay-resolve="desktop" data-relay-action="forwarded"/);
  assert.match(review,/data-relay-resolve="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" data-relay-action="forwarded"/);
  await run("resolveTelegramRelay('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','retry')");
  assert.equal(pending.length,0,'review without explicit acknowledgement does not write');
  element('#relay-ack-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa').checked=true;
  const resolution=run("resolveTelegramRelay('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','retry')");
  const resolving=pending.pop();
  assert.equal(resolving.url,'/api/telegram-relay/resolve');
  assert.equal(resolving.options.headers['X-Wxbot-Relay-Action'],'1');
  assert.deepEqual(JSON.parse(resolving.options.body),{id:'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',action:'retry',acknowledge:true});
  resolving.resolve({ok:true,json:async()=>({ok:true})});
  await resolution;
  console.log('relay frontend checks passed');
}
checks().catch(error=>{console.error(error);process.exitCode=1});
'''
    result = subprocess.run([node, '-e', script], cwd=root, capture_output=True, text=True,
                            encoding='utf-8', timeout=15)
    assert result.returncode == 0, result.stderr
    assert 'relay frontend checks passed' in result.stdout
