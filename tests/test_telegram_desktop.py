"""Desktop relay coordination uses fake steps; never touches native UI."""
import json
from types import SimpleNamespace
from datetime import datetime,timezone
import time

from butler.channels.telegram.relay.store import RelayStore


def observation(key):
    return {'key':key,'text':key,'runtime_id':[1,len(key)],'source_url':''}


def test_first_scan_baselines_then_new_rows_are_persisted_without_duplicates(tmp_path):
    store=RelayStore(tmp_path/'relay.db')
    assert store.capture('a',[observation('old')],now=1)==0
    assert store.capture('a',[observation('old'),observation('new')],now=2)==1
    assert store.capture('a',[observation('old'),observation('new')],now=3)==0
    assert store.claim(['a'])['payload']['key']=='new'


def test_per_channel_order_fairness_and_unknown_recovery(tmp_path):
    store=RelayStore(tmp_path/'relay.db')
    for channel in ('a','b'):
        store.capture(channel,[observation('old')],now=1)
        store.capture(channel,[observation('old'),observation('one'),observation('two')],now=2)
    first=store.claim(['a','b']); assert first['channel']=='a'
    store.finish(first['id'],'forwarded')
    second=store.claim(['a','b']); assert second['channel']=='b'
    store.mark_submitted(second['id'])
    RelayStore(tmp_path/'relay.db').recover()
    assert store.status()['counts']['uncertain']==1
    assert store.claim(['a','b'])['channel']=='a'


def test_source_id_confirmation_deduplicates_without_text_guessing(tmp_path):
    store=RelayStore(tmp_path/'relay.db')
    store.capture('a',[],now=1)
    store.capture('a',[observation('same'),observation('same')],now=2)
    first=store.claim(['a']); assert store.bind_source(first['id'],'123')
    store.finish(first['id'],'forwarded')
    second=store.claim(['a']); assert not store.bind_source(second['id'],'123')
    assert store.status()['counts']['duplicate']==1


def test_gap_preserves_checkpoint_and_requires_calibration_instead_of_history_replay(tmp_path):
    store=RelayStore(tmp_path/'relay.db')
    store.capture('a',[observation('old')],now=1)
    assert store.capture('a',[observation('unrelated')],now=2)==0
    assert 'gap' in store.status()['channels'][0]['error']
    assert store.claim(['a']) is None


def test_disabled_config_never_activates_desktop(tmp_path):
    from wxbot.telegram_desktop import DesktopRelay
    class Driver:
        def scan(self,*a): raise AssertionError('disabled must not touch desktop')
    relay=DesktopRelay(tmp_path/'missing.toml',tmp_path/'state',Driver())
    assert not relay.tick() and not relay.busy


def test_unified_scheduler_never_interleaves_relay_and_wechat_transactions():
    from wxbot.inbox import MainInbox
    inbox=MainInbox.__new__(MainInbox)
    calls=[]
    inbox.telegram=SimpleNamespace(busy=True,tick=lambda:calls.append('telegram'))
    inbox.delivery=SimpleNamespace(busy=False)
    inbox.tick()
    assert calls==['telegram']


def test_only_fresh_matching_bot_ingress_confirms_native_forward(tmp_path):
    store=RelayStore(tmp_path/'relay.db')
    store.capture('a',[],now=1);store.capture('a',[observation('new')],now=2)
    task=store.claim(['a'])
    store.bind_source(task['id'],'42',source_chat_id=-100123,source_username='source')
    store.mark_submitted(task['id']);store.finish(task['id'],'awaiting_bot')
    receipt={'source_chat_id':-100123,'source_username':'source','source_message_id':42,
             'received_at':datetime.now(timezone.utc).isoformat()}
    store.reconcile_receipts([{**receipt,'source_chat_id':-100999}])
    assert store.status()['counts']=={'awaiting_bot':1}
    store.reconcile_receipts([{**receipt,'received_at':'2020-01-01T00:00:00+00:00'}])
    assert store.status()['counts']=={'awaiting_bot':1}
    store.reconcile_receipts([receipt])
    assert store.status()['counts']=={'forwarded':1}


def test_bot_receipt_timeout_does_not_replay_and_other_channels_continue(tmp_path):
    store=RelayStore(tmp_path/'relay.db')
    for channel in ('a','b'):
        store.capture(channel,[]);store.capture(channel,[observation('one'),observation('two')])
    task=store.claim(['a']);store.bind_source(task['id'],'42',source_username='source')
    store.mark_submitted(task['id']);store.finish(task['id'],'awaiting_bot')
    assert store.claim(['a']) is None
    assert store.claim(['a','b'])['channel']=='b'
    store.reconcile_receipts([],now=time.time()+61)
    assert store.status()['counts']['uncertain']==1 and store.claim(['a']) is None
    store.reconcile_receipts([{'source_username':'SOURCE','source_message_id':42,'received_at':datetime.now(timezone.utc).isoformat()}])
    assert store.status()['counts']['forwarded']==1


def test_recovery_claims_persisted_ui_hold_before_either_app_runs(tmp_path):
    from wxbot.telegram_desktop import DesktopRelay
    path=tmp_path/'state'/'desktop.sqlite3'
    store=RelayStore(path);store.capture('a',[]);store.capture('a',[observation('one')]);store.claim(['a'])
    relay=DesktopRelay(tmp_path/'missing.toml',path.parent,driver=object())
    assert relay.requires_ui_review and not relay.tick()
    assert store.status()['counts']['blocked']==1


def test_reusing_channel_key_baselines_new_source_and_does_not_false_dedup(tmp_path):
    from butler.channels.telegram.relay.settings import Channel
    store=RelayStore(tmp_path/'relay.db')
    first=Channel('a','first',username='first');second=Channel('a','second',username='second')
    store.sync_channels([first]);store.capture('a',[]);store.capture('a',[observation('old')])
    task=store.claim(['a']);store.bind_source(task['id'],'42',source_username='first');store.finish(task['id'],'forwarded')
    store.capture('a',[observation('old'),observation('unsent')])
    store.sync_channels([second]);assert store.capture('a',[observation('baseline')])==0
    store.capture('a',[observation('baseline'),observation('new')]);new=store.claim(['a'])
    assert new['payload']['key']=='new' and store.bind_source(new['id'],'42',source_username='second')
    assert store.status()['counts']['cancelled']==1


def relay_config(tmp_path,channels=None):
    from butler.channels.telegram.relay.settings import Settings
    path=tmp_path/'relay.toml';settings=Settings(path)
    settings.update({'enabled':True,'bot_id':123,'bot_username':'Test_bot','channels':channels or
                    [{'key':'a','name':'Source','username':'source','enabled':True}]},settings.read()['version'])
    identity=tmp_path/'telegram-bot'/'bot-identity.json';identity.parent.mkdir(exist_ok=True)
    identity.write_text(json.dumps({'bot_id':123,'username':'Test_bot'}),encoding='utf-8')
    return path


def test_interrupted_scan_persists_desktop_ownership_for_restart(tmp_path):
    from wxbot.telegram_desktop import DesktopRelay
    path=relay_config(tmp_path)
    driver=SimpleNamespace(scan=lambda *a:SimpleNamespace(step=lambda:None,close=lambda:False,requires_review=True))
    relay=DesktopRelay(path,tmp_path/'state',driver)
    assert relay.tick() and relay.busy
    restarted=DesktopRelay(path,tmp_path/'state',driver)
    assert restarted.requires_ui_review
    assert restarted.store.status()['tasks'][0]['id']=='desktop'
    assert not restarted.tick()


def test_scan_and_forward_take_turns_despite_another_channels_backlog(tmp_path):
    from wxbot.telegram_desktop import DesktopRelay
    path=relay_config(tmp_path,[{'key':c,'name':c,'username':'source_'+c,'enabled':True} for c in ('a','b')])
    calls=[]
    class Driver:
        def scan(self,channel,*args):
            calls.append(('scan',channel.key))
            return SimpleNamespace(step=lambda:{'state':'scanned','observations':[observation('old')]},close=lambda:True)
        def forward(self,channel,payload,settings,on_source,on_submit):
            calls.append(('forward',channel.key))
            return SimpleNamespace(step=lambda:{'state':'blocked'},close=lambda:True)
    relay=DesktopRelay(path,tmp_path/'state',Driver())
    relay.tick()
    relay.store.capture('a',[observation('old'),*[observation(str(n)) for n in range(100)]])
    relay.tick();relay.tick()
    assert calls==[('scan','a'),('forward','a'),('scan','b')]


def test_uncertain_closed_modal_cleanup_failure_stays_resolvable(tmp_path):
    from wxbot.telegram_desktop import DesktopRelay
    path=relay_config(tmp_path)
    relay=DesktopRelay(path,tmp_path/'state',SimpleNamespace())
    relay.store=RelayStore(tmp_path/'state'/'desktop.sqlite3')
    relay.store.capture('a',[]);relay.store.capture('a',[observation('one')]);relay.task=relay.store.claim(['a'])
    task_id=relay.task['id']
    relay.active=SimpleNamespace(close=lambda:False,submitted=True,requires_review=True)
    relay.store.finish(task_id,'awaiting_bot');relay._release()
    assert relay.requires_ui_review and relay.store.status()['counts']=={'uncertain':1}
    assert relay.store.resolve(task_id,'cancelled')['ok'] and not relay.requires_ui_review


def test_same_semantic_message_with_changed_native_identity_is_visible_ambiguity(tmp_path):
    store=RelayStore(tmp_path/'relay.db')
    store.capture('a',[{**observation('same'),'runtime_id':[10]}])
    store.capture('a',[{**observation('same'),'runtime_id':[11]}])
    assert 'ambiguous' in store.status()['channels'][0]['error']
    assert store.claim(['a']) is None


def test_crash_after_native_result_before_cleanup_uses_resolvable_desktop_hold(tmp_path):
    store=RelayStore(tmp_path/'relay.db')
    store.capture('a',[]);store.capture('a',[observation('new')]);task=store.claim(['a'])
    store.begin_ui(task['id'],'a');store.mark_submitted(task['id']);store.finish(task['id'],'awaiting_bot')
    store.recover()
    assert store.status()['tasks'][0]['id']=='desktop'
    assert store.resolve('desktop','cancelled')['ok'] and not store.has_hold()


def test_scan_never_clears_preexisting_human_query_or_unreadable_owned_query(monkeypatch):
    from wxbot.telegram_desktop import _Scan
    from butler.channels.telegram.relay.settings import Channel,RelaySettings
    from wxbot import telegram_desktop as module
    calls=[];monkeypatch.setattr(module.auto,'SendKeys',lambda *a,**kw:calls.append(a))
    scan=_Scan(SimpleNamespace(guard=lambda win:True),Channel('a','Source',username='source'),RelaySettings())
    scan.search=SimpleNamespace(GetValuePattern=lambda:SimpleNamespace(Value='@source'),HasKeyboardFocus=True)
    assert scan.close() and not calls
    scan.query_written=True
    scan.search=SimpleNamespace(GetValuePattern=lambda:(_ for _ in ()).throw(ValueError()),Exists=lambda _:True)
    assert not scan.close() and not calls
