"""Bounded, UI-thread-only image paste/preview/send transaction."""
from io import BytesIO
from pathlib import Path
import time

import uiautomation as auto
from PIL import Image
from .clipboard import ImageClipboardLease, failure_details


class ImageSession:
    def __init__(self, chat, win, edit, path, *, clock=time.monotonic,
                 clipboard_factory=ImageClipboardLease, send_keys=auto.SendKeys):
        from butler.delivery.media import validate_image, MAX_BYTES
        path=Path(path)
        if path.stat().st_size>MAX_BYTES:
            raise ValueError('图片超过大小上限')
        data=path.read_bytes()
        validate_image(data)
        with Image.open(BytesIO(data)) as image:
            buffer=BytesIO()
            image.convert('RGB').save(buffer,format='BMP')
            self.dib=buffer.getvalue()[14:]
        self.chat,self.win,self.edit=chat,win,edit
        self.clock,self.clipboard_factory,self.send_keys=clock,clipboard_factory,send_keys
        self.state,self.error='typing',''
        self.enter_attempted=False
        self.before_enter=None
        self.on_verified_draft=None
        self.failure_details={}
        self.submitted_text=None
        self.phase='paste'
        self._clipboard=None
        self._pasted=False
        self._deadline=clock()+2
        self._preview=None
        self._preview_draft_proof=None
        self.baseline_images=[]

    def close(self):
        if self._clipboard is None:
            return True
        if self._clipboard.close():
            self._clipboard=None
            return True
        self.failure_details.update(self._clipboard.restore_failure)
        return False

    def resume_after_authorization_pause(self,seconds):
        self._deadline+=seconds

    def _block(self, reason):
        self.error=reason
        self.state='uncertain' if self.enter_attempted else 'blocked'
        self.failure_details.update(phase=self.phase,enter_attempted=self.enter_attempted,
                                    manual_required=self._pasted)
        self.close()
        return self.state

    def _draft_proof(self,preview):
        if self.chat._input_text(self.edit)!='':
            return None
        probe=getattr(self.chat,'image_preview_draft',None)
        if probe is None:
            return None
        proof=probe(preview)
        if proof is None or any(value!='' for identity,value in proof):
            return None
        return proof

    def step(self):
        if self.state!='typing':
            return self.state
        try:
            if self.phase=='paste':
                if not self.chat._can_send(self.win,self.edit) or self.chat._input_text(self.edit)!='':
                    return self._block('图片粘贴前会话、焦点或草稿变化')
                self._clipboard=self.clipboard_factory(self.dib)
                if (not self.chat._can_send(self.win,self.edit) or self.chat._input_text(self.edit)!=''
                        or not self._clipboard.is_current()):
                    return self._block('图片粘贴前剪贴板、会话或草稿变化')
                # A native paste can mutate UI and then raise. Treat that as an owned draft conflict.
                self._pasted=True
                self.send_keys('{Ctrl}v',interval=0.01,waitTime=0.05)
                self.phase='preview'
                self._deadline=self.clock()+2
            elif self.phase=='preview':
                if not self.chat.target_is_current(self.win):
                    return self._block('图片预览期间会话或前台窗口变化')
                if self.chat._input_text(self.edit)!='':
                    return self._block('图片预览期间原输入框内容变化或不可读')
                preview=self.chat.image_preview(self.win)
                if preview is None:
                    if self.clock()>=self._deadline:
                        return self._block('图片预览未出现或控件未校准，未点击发送')
                    return self.state
                proof=self._draft_proof(preview[0])
                if proof is None:
                    return self._block('图片预览说明或原输入框变化、不可读，未点击发送')
                if not self._clipboard.is_current():
                    return self._block('图片预览期间剪贴板被其他操作更改')
                if not self.close():
                    return self._block('图片剪贴板未恢复，未点击发送')
                self._preview=preview
                self._preview_draft_proof=proof
                self.phase='submit'
            elif self.phase=='submit':
                if self.clock()>=self._deadline:
                    return self._block('图片预览等待超时，未点击发送')
                preview,button=self._preview
                if not self.chat.image_preview_is_current(self.win,preview,button):
                    return self._block('图片发送前会话、前台或预览变化')
                if self._draft_proof(preview)!=self._preview_draft_proof:
                    return self._block('图片发送前原输入框或预览说明变化、不可读')
                self.baseline_images=self.chat.image_bubbles(self.win)
                if self.before_enter is not None:
                    if self.before_enter() is False:
                        self._deadline=self.clock()+2
                        return self.state
                if not self.chat.image_preview_is_current(self.win,preview,button):
                    return self._block('图片发送前目标再次校验失败')
                if self._draft_proof(preview)!=self._preview_draft_proof:
                    return self._block('图片提交前原输入框或预览说明再次变化、不可读')
                self.enter_attempted=True
                self.chat.submit_image_preview(button)
                self.state='submitted'
        except Exception as exc:
            self.failure_details.update(failure_details(exc))
            return self._block('图片操作失败: '+type(exc).__name__)
        return self.state

    def confirmation_visible(self):
        if not self.enter_attempted or not self.chat.target_is_current(self.win):
            return False
        before={tuple(item['id']) for item in self.baseline_images}
        current=self.chat.image_bubbles(self.win)
        after={tuple(item['id']) for item in current}
        if not before<=after or len(after)<=len(before):
            return False
        return any(item['sender']=='self' and tuple(item['id']) not in before
                   for item in current)
