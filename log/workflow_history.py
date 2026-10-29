"""Explicit dashboard history edits against a fixed, configured queue path."""
from pathlib import Path

from wxbot.queue_store import QueueStore
from wxbot.queue_history import WorkflowConflict,validate


class WorkflowHistory:
    def __init__(self,path):self.path=Path(path)

    def delete(self,payload):
        validate(payload)
        if not self.path.is_file():raise ValueError('队列尚未创建')
        store=QueueStore(self.path,access='admin')
        try:return store.delete_workflow_history(payload)
        finally:store.close()
