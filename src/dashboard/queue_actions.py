"""Explicit dashboard recovery actions; never touch UI or invoke shell commands."""
import math
from pathlib import Path
import re
import time
import sqlite3
import tomllib
import uuid

from wxbot.queue_store import QueueStore


class QueueActions:
    def __init__(self,path):
        self.path=Path(path)

    def delete_unsent(self, payload, *, telegram_config=None, now=None):
        if not isinstance(payload, dict) or set(payload) != {'acknowledge'} or payload['acknowledge'] is not True:
            raise ValueError('请确认删除所有未发送成功消息')
        now = time.time() if now is None else now
        empty = dict(deleted_messages=0, deleted_deliveries=0, protected_active=0)
        result = {'ok': True, 'wxbot': dict(empty), 'telegram': dict(empty)}
        errors = []
        if self.path.is_file():
            store = None
            try:
                store = QueueStore(self.path, access='admin')
                result['wxbot'] = store.delete_unsent(now=now, source='log')
            except (ValueError, OSError, sqlite3.Error) as exc:
                errors.append('微信删除失败（'+type(exc).__name__+'）')
            finally:
                if store is not None:
                    store.close()
        if telegram_config is not None and Path(telegram_config).is_file():
            try:
                config_path = Path(telegram_config).resolve()
                config = tomllib.loads(config_path.read_text(encoding='utf-8-sig'))['telegram_bot']
                path = (config_path.parent / config.get('state_dir', 'data/telegram-bot') / 'relay.sqlite3').resolve()
                if path.is_file():
                    from butler.channels.telegram.bot.cleanup import delete_unsent
                    directory = path.parent / 'backups'
                    directory.mkdir(parents=True, exist_ok=True)
                    backup_path = directory / ('delete-unsent-' + uuid.uuid4().hex + '.sqlite3')
                    result['telegram'] = delete_unsent(path, now=now, backup_path=backup_path)
                    result['telegram']['backup_path'] = str(backup_path)
            except (KeyError, TypeError, ValueError, OSError, sqlite3.Error) as exc:
                errors.append('Telegram 删除失败（'+type(exc).__name__+'）')
        if errors:
            result['ok'] = False
            result['error'] = ('；'.join(errors) + '。已删除微信投递 ' + str(result['wxbot']['deleted_deliveries'])
                               + ' 项，Telegram 投递 ' + str(result['telegram']['deleted_deliveries']) + ' 项，请刷新核对。')
        return result

    def perform(self,payload,*,now=None):
        if not isinstance(payload,dict) or payload.get('acknowledge') is not True:
            raise ValueError('请先核对实际微信发送结果，再确认操作')
        record_id=payload.get('id')
        kind,action,contact=payload.get('kind'),payload.get('action'),payload.get('contact')
        if not isinstance(record_id,str) or not re.fullmatch(r'[A-Za-z0-9:_-]{1,128}',record_id):
            raise ValueError('任务ID无效')
        if kind not in {'outbox','batches'} or action not in {'retry','sent','skip'}:
            raise ValueError('不支持的队列操作')
        if not isinstance(contact,str) or not contact or len(contact)>256:
            raise ValueError('必须指定任务联系人')
        # A timed-out delivery can remain skipped with a draft hold; the store
        # checks manual_required and the exact snapshot inside its transaction.
        states={'blocked','uncertain','skipped'} if kind=='outbox' else {'blocked','uncertain'}
        if payload.get('expected_state') not in states or 'expected_finished_at' not in payload:
            raise ValueError('缺少任务快照，请刷新队列')
        finished=payload['expected_finished_at']
        if finished is not None and (type(finished) not in (int,float) or not math.isfinite(finished)):
            raise ValueError('任务快照时间无效')
        if action=='sent' and kind!='outbox':
            raise ValueError('只有发件任务可以确认已发送')
        if kind=='batches' and (type(payload.get('expected_attempts')) is not int or payload['expected_attempts']<0):
            raise ValueError('缺少任务执行次数，请刷新队列')
        if not self.path.is_file():
            raise ValueError('队列尚未创建')
        store=QueueStore(self.path,access='admin')  # No creation, migration, runtime lock or recover.
        now=time.time() if now is None else now
        try:
            options={'delivery':kind=='outbox','contact':contact,'expected_state':payload['expected_state'],
                     'expected_finished_at':finished,'source':'log','now':now}
            if kind=='batches':options['expected_attempts']=payload['expected_attempts']
            if action=='retry':store.retry(record_id,**options)
            else:store.resolve(record_id,sent=action=='sent',**options)
            print(f'[队列人工核对][{contact}][{record_id}] {kind} 操作={action}',flush=True)
            return {'ok':True,'id':record_id,'action':action}
        finally:
            store.close()
