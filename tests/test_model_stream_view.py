from contextlib import closing
import json
import sqlite3

import pytest

from wxbot.queue_store import QueueStore, Incoming


def test_model_identity_uses_direct_selection_and_optional_display_name():
    from log.model_stream_view import resolve_model
    info=resolve_model({'installation':{'mode':'direct','provider':'deepseek'},
        'model':{'backend':'openai','model':'selected-model'}},{'agent':{'provider':'codex'}})
    assert info=={'provider':'deepseek','label':'DeepSeek','model':'selected-model','via_butler':False}
    assert resolve_model({'model':{'backend':'hermes','model':'agent-model'}}, {})['label']=='Hermes'
    assert resolve_model({'model':{'backend':'responses','display_name':'我的智能体'}}, {})['label']=='我的智能体'


def test_model_identity_local_and_unknown_external_are_truthful():
    from log.model_stream_view import resolve_model
    assert resolve_model({'model':{'backend':'butler'}}, {'agent':{'provider':'hermes'},'hermes':{'model':'agent'}})=={
        'provider':'hermes','label':'Hermes','model':'agent','via_butler':True}
    info=resolve_model({'installation':{'mode':'external'},'model':{'backend':'butler'}},{'agent':{'provider':'codex'}})
    assert info['label']=='外部智能体' and info['model']==''


def test_stream_read_is_bounded_readonly_and_excludes_private_events(tmp_path):
    from log.model_stream_view import read_stream
    path=tmp_path/'queue.db'
    with closing(QueueStore(path)) as store:
        store.capture('A',[],[Incoming('question')],now=1)
        store.prepare(quiet=0,max_wait=1,prefix='/',now=2)
        rid=store.claim_batch(now=3).id
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS model_stream_events(seq INTEGER PRIMARY KEY AUTOINCREMENT,batch_id TEXT NOT NULL,event TEXT NOT NULL,created_at REAL NOT NULL)')
            for event in [{'type':'backend','provider':'hermes','model':'chosen','streaming':True},
                          {'type':'summary_delta','text':'公开摘要'}, {'type':'answer_delta','text':'你好','sendable':True},
                          {'type':'reasoning','text':'private'}, {'type':'tool','tool':'lookup','status':'running','arguments':'secret'}]:
                db.execute('INSERT INTO model_stream_events(batch_id,event,created_at) VALUES(?,?,?)',(rid,json.dumps(event),4))
            before=db.execute('SELECT COUNT(*) FROM model_stream_events').fetchone()[0]
        data=read_stream(path,rid)
        assert data['available'] and data['cursor']>0
        assert [e['type'] for e in data['events']]==['backend','summary_delta','answer_delta','tool']
        assert 'private' not in str(data) and 'arguments' not in str(data)
        assert read_stream(path,rid,after=data['cursor'])['events']==[]
        with sqlite3.connect(path) as db:assert db.execute('SELECT COUNT(*) FROM model_stream_events').fetchone()[0]==before


def test_stream_read_missing_database_or_table_never_initializes_it(tmp_path):
    from log.model_stream_view import read_stream
    missing=tmp_path/'missing.db'
    assert not read_stream(missing,'batch-id')['available']
    assert not missing.exists()
    path=tmp_path/'old.db'
    with sqlite3.connect(path) as db:db.execute('CREATE TABLE old(value TEXT)')
    assert not read_stream(path,'batch-id')['available']
    with sqlite3.connect(path) as db:assert db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='model_stream_events'").fetchone()[0]==0


@pytest.mark.parametrize('rid,after',[('../file',0),('batch',-1),('batch',True),('batch','1')])
def test_stream_rejects_invalid_cursor_and_id(tmp_path,rid,after):
    from log.model_stream_view import read_stream
    with pytest.raises(ValueError):read_stream(tmp_path/'no.db',rid,after=after)


def test_reply_mode_has_editor_choices_and_validation():
    from log.config_schema import row_metadata,validate_value
    meta=row_metadata('wxbot',['wechat','typing','mode'],'chunked')
    assert meta['choices']==['full','chunked','streaming'] and meta['label']=='回复方式'
    validate_value(['wechat','typing','mode'],'streaming','chunked')
    with pytest.raises(ValueError):validate_value(['wechat','typing','mode'],'other','chunked')


def test_workflow_handler_direct_mode_does_not_require_butler_config(tmp_path,monkeypatch):
    from log.config_view import ConfigView
    from log import server
    from types import SimpleNamespace
    path=tmp_path/'queue.db'
    with closing(QueueStore(path)) as store:store.capture('A',[],[Incoming('question')],now=1)
    wx=tmp_path/'wx.toml'
    wx.write_text('[installation]\nmode="direct"\nprovider="deepseek"\n[model]\nbackend="openai"\nmodel="chosen"\n[queue]\ndatabase="queue.db"\n',encoding='utf-8')
    config=ConfigView(wx,tmp_path/'missing-butler.toml',tmp_path,repo_root=tmp_path,log_config_path=tmp_path/'missing-log.toml')
    monkeypatch.setattr(server,'load_wxbot_contacts',lambda:[])
    monkeypatch.setattr(server,'_load_butler_config',lambda:(_ for _ in ()).throw(AssertionError('must not load Butler')))
    handler=server.Handler.__new__(server.Handler);handler.path='/api/workflow'
    handler._config_view=lambda:config
    result=[];handler._json=lambda payload,code=200:result.append((code,payload))
    handler.do_GET()
    assert result[0][0]==200 and result[0][1]['model']['label']=='DeepSeek'
    assert not (tmp_path/'missing-butler.toml').exists()
