import pytest

from wxbot.queue_admin import main
from wxbot.queue_store import QueueStore


def test_uncertain_retry_requires_explicit_acknowledgement(tmp_path):
    path = tmp_path / "queue.sqlite3"
    store = QueueStore(path)
    record_id = store.enqueue_delivery("A", "回答", now=0)
    store.claim_delivery(now=0)
    store.recover()
    with pytest.raises(SystemExit):
        main(["--database", str(path), "retry", record_id, "--delivery"])
    assert store.get_delivery(record_id)["state"] == "uncertain"
    assert main(["--database", str(path), "retry", record_id, "--delivery", "--acknowledge"]) == 0
    assert store.get_delivery(record_id)["state"] == "pending"
    store.close()


def test_status_does_not_recover_or_modify_a_running_ui_task(tmp_path, capsys):
    path = tmp_path / "queue.sqlite3"
    store = QueueStore(path)
    record_id = store.enqueue_delivery("A", "回答", now=0)
    store.claim_delivery(now=0)
    assert main(["--database", str(path), "status"]) == 0
    assert store.get_delivery(record_id)["state"] == "sending"
    assert '"sending": 1' in capsys.readouterr().out
    store.close()


def test_manual_resolution_cannot_override_an_active_task(tmp_path):
    path = tmp_path / "queue.sqlite3"
    store = QueueStore(path)
    record_id = store.enqueue_delivery("A", "回答", now=0)
    store.claim_delivery(now=0)
    assert main(["--database", str(path), "sent", record_id]) == 2
    assert main(["--database", str(path), "skip", record_id, "--delivery"]) == 2
    assert store.get_delivery(record_id)["state"] == "sending"
    store.recover()
    assert main(["--database", str(path), "sent", record_id]) == 0
    assert store.get_delivery(record_id)["state"] == "sent"
    store.close()


def test_legacy_status_and_list_are_readonly(tmp_path,capsys):
    from test_queue_migration import legacy
    path=tmp_path/'legacy.db'
    legacy(path)
    before=path.read_bytes()
    assert main(['--database',str(path),'status'])==0
    assert main(['--database',str(path),'list'])==0
    assert '1/1' in capsys.readouterr().out
    assert path.read_bytes()==before
    assert main(['--database',str(path),'sent','d7'])==2


def test_multipart_cli_sent_and_retry_preserve_other_parts(tmp_path,capsys):
    from test_queue_migration import batch
    path=tmp_path/'q.db'
    store=QueueStore(path)
    a=batch(store,'A',['a1','a2','a3'])
    d=store.claim_delivery(now=0)
    store.finish_delivery(d.id,'sent',now=0)
    d=store.claim_delivery(now=0)
    store.finish_delivery(d.id,'uncertain',now=0)
    assert main(['--database',str(path),'sent',d.id])==0
    assert store.get_batch(a.id)['state']=='waiting_delivery'
    d=store.claim_delivery(now=0)
    store.finish_delivery(d.id,'blocked',now=0)
    assert main(['--database',str(path),'retry',d.id,'--delivery','--acknowledge'])==0
    assert store.claim_delivery(now=0).text=='a3'
    assert main(['--database',str(path),'list','--all'])==0
    output=capsys.readouterr().out
    assert '2/3' in output and '3/3' in output
    store.close()
