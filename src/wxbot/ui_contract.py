"""UI 快照与失败契约：动作只对属于本次快照的行生效，失败一律带稳定代码。

一次读取产生一个快照，快照里每一行带一个只属于这次读取的引用（行控件的运行期
标识）。动作前后都要重新取快照核对，所以「同一句话别人也发过」「发送方判定抖动」
这类情况下，判定依据是 **这一行是不是新的**，而不是「这段文字出现过没有」。

引用拿不到或不唯一时必须显式降级为正文对齐，并把降级事实写进诊断字段；不能假装
两者没有区别。代码给队列、看板和测试看，中文句子只面向人。
"""
from dataclasses import dataclass

from .state import overlap_end

# 重试语义：never 重放会重复副作用或必然再失败；after_snapshot 必须重新读一次界面。
NEVER = 'never'
AFTER_SNAPSHOT = 'after_snapshot'

DISPOSITIONS = {
    'target_unavailable': AFTER_SNAPSHOT,
    'target_changed': AFTER_SNAPSHOT,
    'focus_lost': AFTER_SNAPSHOT,
    'clipboard_owner_changed': AFTER_SNAPSHOT,
    'paste_error': AFTER_SNAPSHOT,
    'draft_conflict': NEVER,
    'paste_mismatch': NEVER,
    'enter_unconfirmed': NEVER,
    'sticker_unconfirmed': NEVER,
    'sticker_unavailable': NEVER,
    'ui_error': NEVER,
}
UNKNOWN_CODE = 'ui_error'


def failure(code, **details):
    """失败信封：稳定代码 + 重试语义。只放标量，正文、剪贴板内容和凭据都不进来。"""
    known = code if code in DISPOSITIONS else UNKNOWN_CODE
    data = {'error_code': known, 'retry': DISPOSITIONS[known]}
    data.update({key: value for key, value in details.items() if value is not None})
    return data


def disposition(code):
    return DISPOSITIONS.get(code, DISPOSITIONS[UNKNOWN_CODE])


def normalize_text(value):
    return (value or '').replace('\r\n', '\n').replace('\r', '\n').strip()


def row_key(message):
    """行的身份：优先用控件运行期标识，没有才退回正文。"""
    ref = getattr(message, 'ref', '') or ''
    return 'ref:' + ref if ref else 'text:' + normalize_text(getattr(message, 'text', ''))


def persisted_rows(rows):
    """引用只在本次读取内有效：落库时不保存，重启后只能按正文对齐。"""
    from dataclasses import asdict
    return [{key: value for key, value in
             (row.items() if isinstance(row, dict) else asdict(row).items()) if key != 'ref'}
            for row in rows or ()]


@dataclass(frozen=True)
class Snapshot:
    """一次读取的结果。行只能整批比较，不能把一个快照的行拿去当另一个快照的引用。"""
    rows: tuple = ()

    def __post_init__(self):
        refs = tuple(getattr(row, 'ref', '') or '' for row in self.rows)
        object.__setattr__(self, 'refs', refs)
        # 引用要「全有且唯一」才算可信：缺一个、或微信复用了行控件，都退回正文对齐。
        object.__setattr__(self, 'ref_complete',
                           bool(self.rows) and all(refs) and len(set(refs)) == len(refs))

    @classmethod
    def take(cls, messages):
        return cls(tuple(messages or ()))

    def sent_after(self, previous, text):
        """返回 (证据, 行)：证据是 'ref' 或 'text'，都不成立时 (None, None)。"""
        target = normalize_text(text)
        if not target:
            return None, None
        previous = previous if isinstance(previous, Snapshot) else Snapshot.take(previous)
        if self.ref_complete and previous.ref_complete:
            known = {row_key(row) for row in previous.rows}
            for row in self.rows:
                if row_key(row) in known:
                    continue
                if row.sender == 'self' and normalize_text(row.text) == target:
                    return 'ref', row
            # 引用完整时，正文相同但引用来历不明的行不算证据。
            return None, None
        if not previous.rows:
            delta = self.rows
        else:
            end = overlap_end(list(previous.rows), list(self.rows))
            if end is None:
                return None, None
            delta = self.rows[end:]
        for row in delta:
            if row.sender == 'self' and normalize_text(row.text) == target:
                return 'text', row
        return None, None

    def evidence_available(self, previous):
        """两个快照的引用都完整时，确认结果才是引用级证据。"""
        previous = previous if isinstance(previous, Snapshot) else Snapshot.take(previous)
        return bool(self.ref_complete and previous.ref_complete)
