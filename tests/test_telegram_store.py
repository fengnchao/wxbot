from datetime import datetime, timezone
import sqlite3

import pytest


def msg(number=1, text='同一新闻'):
    from butler.telegram.formatting import Message
    return Message(-100123, number, text, datetime(2026, 10, 22, tzinfo=timezone.utc), '早报', 'zaobaosg')


def store(tmp_path):
    from butler.telegram.store import Store
    s = Store(tmp_path / 'relay.sqlite3')
    s.bind(9, -100123, 'zaobaosg', 0)
    return s


def test_binding_rejects_account_and_source_change_and_preserves_cursor(tmp_path):
    s = store(tmp_path)
    s.ingest(-100123, [msg()], 1)
    s.bind(9, -100123, 'zaobaosg', 100)
    assert s.cursor(-100123) == 1
    with pytest.raises(ValueError):
        s.bind(10, -100123, 'zaobaosg', 0)
    with pytest.raises(ValueError):
        s.bind(9, -100456, 'zaobaosg', 0)
    s.close()


def test_dedupe_uses_message_id_not_text_and_survives_reopen(tmp_path):
    from butler.telegram.store import Store
    s = store(tmp_path)
    s.ingest(-100123, [msg(), msg(2)], 2)
    s.ingest(-100123, [msg(2)], 2)
    s.close()
    s = Store(tmp_path / 'relay.sqlite3')
    assert s.cursor(-100123) == 2
    assert [m.message_id for m in s.unexpanded()] == [1, 2]
    s.close()


def test_page_failure_rolls_back_messages_and_cursor(tmp_path):
    s = store(tmp_path)
    with sqlite3.connect(tmp_path / 'relay.sqlite3') as db:
        db.execute("CREATE TRIGGER reject_message BEFORE INSERT ON messages WHEN NEW.message_id=2 BEGIN SELECT RAISE(ABORT,'disk fixture'); END")
    with pytest.raises(sqlite3.IntegrityError):
        s.ingest(-100123, [msg(), msg(2)], 2)
    assert s.cursor(-100123) == 0
    assert s.unexpanded() == []
    s.close()


def test_expansion_snapshot_and_claim_do_not_repeat_sent_parts(tmp_path):
    s = store(tmp_path)
    s.ingest(-100123, [msg()], 1)
    s.expand(msg(), ['A', 'B'], ['p1', 'p2'])
    s.expand(msg(), ['C'], ['rewritten'])
    first = s.claim(['A', 'B', 'C'])
    assert (first.contact, first.text, first.part) == ('A', 'p1', 1)
    s.finish(first.id, 'sent', 'confirmed')
    next_part = s.claim(['A', 'B', 'C'])
    assert next_part.id != first.id
    assert s.status()['deliveries']['sent'] == 1
    assert 'C' not in {r['contact'] for r in s.status()['receipts']}
    s.close()


def test_uncertain_blocks_only_affected_recipient_and_restart_does_not_replay(tmp_path):
    s = store(tmp_path)
    s.ingest(-100123, [msg(), msg(2)], 2)
    for m in s.unexpanded():
        s.expand(m, ['A', 'B'], ['p1', 'p2'])
    a = s.claim(['A', 'B'])
    assert a.contact == 'A'
    s.recover()
    assert s.status()['deliveries']['uncertain'] == 1
    b = s.claim(['A', 'B'])
    assert b.contact == 'B'
    s.finish(b.id, 'sent', 'ok')
    b2 = s.claim(['A', 'B'])
    assert (b2.contact, b2.message_id, b2.part) == ('B', 1, 2)
    s.finish(b2.id, 'not_submitted', 'refused')
    assert s.claim(['A', 'B']) is None
    s.close()


def test_empty_group_is_not_reexpanded_and_removed_user_is_skipped(tmp_path):
    s = store(tmp_path)
    s.ingest(-100123, [msg(), msg(2), msg(3, '  ')], 3)
    s.expand(msg(), [], ['body'])
    s.expand(msg(), ['A'], ['body'])
    s.expand(msg(2), ['A', 'B'], ['body'])
    d = s.claim(['B'])
    assert (d.contact, d.message_id) == ('B', 2)
    report = s.status()
    assert report['messages']['no_subscribers'] == 1
    assert report['messages']['ignored'] == 1
    assert report['deliveries']['skipped_removed'] == 1
    s.close()


def test_status_readonly_does_not_modify_database(tmp_path):
    from butler.telegram.store import Store
    s = store(tmp_path)
    s.close()
    path = tmp_path / 'relay.sqlite3'
    before = path.read_bytes()
    ro = Store(path, readonly=True)
    assert ro.status()['sources'][0]['cursor'] == 0
    with pytest.raises(ValueError):
        ro.recover()
    ro.close()
    assert path.read_bytes() == before


def test_inactive_sources_do_not_starve_active_backlog(tmp_path):
    from dataclasses import replace
    s = store(tmp_path)
    s.bind(9, -100456, 'another_source', 0)
    s.ingest(-100123, [msg(n) for n in range(1, 102)], 101)
    active = replace(msg(), source_id=-100456, source_username='another_source')
    s.ingest(-100456, [active], 1)
    assert s.unexpanded(source_ids={-100456}) == [active]
    s.expand(msg(), ['A'], ['old pending'])
    s.expand(active, ['A'], ['active pending'])
    delivery = s.claim(['A'], source_ids={-100456})
    assert delivery.source_id == -100456
    s.finish(delivery.id, 'uncertain', 'unknown')
    # Re-enabling older pending work must not bypass an unknown result.
    assert s.claim(['A'], source_ids={-100123}) is None
    assert s.status()['deliveries']['pending'] == 1
    s.close()


def test_status_counts_complete_recipients_only_after_every_part_confirmed(tmp_path):
    s = store(tmp_path)
    s.ingest(-100123, [msg()], 1)
    s.expand(msg(), ['A', 'B'], ['first', 'second'])
    first = s.claim(['A', 'B'])
    s.finish(first.id, 'sent', 'confirmed')
    assert s.status()['message_results'][0]['completed_recipients'] == 0
    second = s.claim(['A', 'B'])
    s.finish(second.id, 'sent', 'confirmed')
    b = s.claim(['A', 'B'])
    s.finish(b.id, 'uncertain', 'unknown')
    report = s.status()['message_results'][0]
    assert report['message_id'] == 1
    assert report['planned_recipients'] == 2
    assert report['completed_recipients'] == 1
    s.close()
