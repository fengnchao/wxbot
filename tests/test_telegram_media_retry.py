import json
from types import SimpleNamespace

import pytest


def failed_package(tmp_path):
    from butler.telegram_bot.queue import Queue
    from butler.telegram_bot.news import NewsRelay
    queue = Queue(tmp_path / 'relay.sqlite3')
    group = tmp_path / 'groups.json'
    group.write_text('{"groups":{"1":["A"]}}', encoding='utf-8')
    msg = {'message_id':1,'date':1700000000,'from':{'id':12},'chat':{'id':12,'type':'private'},
        'photo':[{'file_id':'p'}], 'media_group_id':'album',
        'forward_origin':{'type':'channel','chat':{'id':-100123},'message_id':42}}
    queue.ingest(99, {'update_id':1}, msg, now=100)
    queue.finish(99,1,'received')
    def fail(message): raise ValueError('temporary fake network failure')
    calls = []
    relay = NewsRelay(queue,99,SimpleNamespace(group_file_path=lambda:group),(12,),lambda s:None,
        media=SimpleNamespace(prepare=fail),
        relay_settings=lambda:SimpleNamespace(include_images=True,include_text=True,album_quiet_seconds=2,max_album_wait=15),
        bundle_push=lambda *args: calls.append(args) or {'state':'sent','reason':'confirmed'}, clock=lambda:103)
    assert relay.expand_once()
    with queue.db() as db:
        key = db.execute('SELECT package_key FROM news_package').fetchone()[0]
    return queue, relay, key, calls


def test_explicit_retry_clears_only_unsubmitted_failed_package_and_service_rebuilds(tmp_path):
    from butler.telegram_bot.news import retry_media_preparation
    queue, relay, key, calls = failed_package(tmp_path)
    result = retry_media_preparation(queue.path,99,key)
    assert result['status']=='retry_ready' and result['reset_updates']==[1]
    assert calls==[]
    with queue.db() as db:
        assert db.execute('SELECT count(*) FROM news_package').fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM news_plan').fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM news_package_alias').fetchone()[0]==0
        assert db.execute('SELECT state FROM pending').fetchone()[0]=='received'
    relay.media.prepare = lambda message:[{'kind':'image','media_id':'a'*32}]
    assert relay.expand_once() and relay.deliver_once()
    assert len(calls)==1


@pytest.mark.parametrize('state', ['pending','sending','sent','uncertain','blocked','not_submitted','cancelled'])
def test_retry_refuses_any_existing_delivery_even_when_package_says_media_failed(tmp_path,state):
    from butler.telegram_bot.news import retry_media_preparation
    queue, relay, key, calls = failed_package(tmp_path)
    with queue.db() as db:
        db.execute('INSERT INTO news_bundle_delivery(bot,package_key,contact,request_id,state) VALUES(99,?,?,?,?)',
                   (key,'A','existing',state))
    before = queue.path.read_bytes()
    with pytest.raises(ValueError,match='投递'):
        retry_media_preparation(queue.path,99,key)
    assert queue.path.read_bytes()==before and calls==[]


@pytest.mark.parametrize('state', ['preparing','ready','skipped','uncertain'])
def test_retry_refuses_nonfailed_or_unknown_package_without_mutation(tmp_path,state):
    from butler.telegram_bot.news import retry_media_preparation
    queue, relay, key, calls = failed_package(tmp_path)
    with queue.db() as db: db.execute('UPDATE news_package SET state=?',(state,))
    before = queue.path.read_bytes()
    with pytest.raises(ValueError): retry_media_preparation(queue.path,99,key)
    assert queue.path.read_bytes()==before
    with pytest.raises(ValueError): retry_media_preparation(queue.path,99,'missing-key')
    assert queue.path.read_bytes()==before


def test_retry_preserves_other_package_aliases_and_plans(tmp_path):
    from butler.telegram_bot.news import retry_media_preparation
    queue, relay, key, calls = failed_package(tmp_path)
    with queue.db() as db:
        db.execute("INSERT INTO news_package(bot,package_key,uid,sender,state) VALUES(99,'other',2,12,'media_failed')")
        db.execute("INSERT INTO news_package_alias VALUES(99,'other-alias','other')")
        db.execute("INSERT INTO news_plan VALUES(99,2,'other-plan')")
    retry_media_preparation(queue.path,99,key)
    with queue.db() as db:
        assert db.execute('SELECT package_key FROM news_package').fetchone()[0]=='other'
        assert db.execute('SELECT alias FROM news_package_alias').fetchone()[0]=='other-alias'
        assert db.execute('SELECT uid FROM news_plan').fetchone()[0]==2


def test_retry_command_requires_existing_queue_and_performs_no_network(tmp_path,monkeypatch,capsys):
    from butler.telegram_bot.__main__ import main
    queue, relay, key, calls = failed_package(tmp_path)
    cfg = tmp_path/'bot.toml'
    cfg.write_text('[telegram_bot]\nstate_dir="."\n',encoding='utf-8')
    monkeypatch.setattr('sys.argv',['telegram_bot','retry-media','--bot-id','99','--package-key',key,'--config',str(cfg)])
    assert main()==0
    result = json.loads(capsys.readouterr().out)
    assert result['status']=='retry_ready' and calls==[]
    from butler.telegram_bot.news import retry_media_preparation
    missing=tmp_path/'missing.sqlite3'
    with pytest.raises((ValueError,FileNotFoundError)):
        retry_media_preparation(missing,99,key)
    assert not missing.exists()
