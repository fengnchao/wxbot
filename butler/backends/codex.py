"""Isolated, bounded official SDK workers; never return unfinished model output."""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import secrets
import re
import shutil
import threading
import time
import uuid
from urllib.request import getproxies

from common.flow_trace import record,current_request_id
from ..concurrency import RuntimeLocks
from ..hermes import HermesError


DEFAULT_POLICY={'role_skill':'butler-companion','allowed_skills':[]}


def owner_key(contact):
    if contact.memory_owner:
        return contact.memory_owner
    return hashlib.sha256(json.dumps([contact.key(),contact.name],ensure_ascii=False).encode()).hexdigest()


def tool_owner_key(contact):
    """Reminders and operation idempotency never inherit a shared memory owner."""
    return 'binding:' + contact.binding_id if contact.binding_id else owner_key(contact)


@dataclass
class Worker:
    client: object
    thread: object
    credential: str
    used: float
    busy: bool = False


class CodexBackend:
    def __init__(self,cfg,log=None,*,locks=None,store,tools,client_factory=None):
        self.cfg,self.store,self.tools=cfg,store,tools
        self.log=log or (lambda *a,**k:None)
        self.locks=locks or RuntimeLocks('codex')
        self.client_factory=client_factory
        self.workers={}
        self._starting=set()
        self._guard=threading.RLock()
        self._slots=threading.BoundedSemaphore(cfg.codex_max_workers)
        self._credentials={}
        self.last_error=''
        # MCP HTTP credentials are opaque to the model. Rotate their signed request
        # context between turns while keeping the worker's HTTP connection reusable.
        self.tools.worker_credentials=self._credentials

    def scope(self,contact,policy=None,kind='chat'):
        policy=self.tools.catalogue.validate(policy or DEFAULT_POLICY)
        return hashlib.sha256(json.dumps([owner_key(contact),contact.key(),contact.memory_version,
            contact.binding_version,policy,kind],sort_keys=True).encode()).hexdigest()

    def session_guard(self,contact,*,skill_policy=None,session_kind='chat'):
        return self.locks.session(contact,session_kind=session_kind)

    def session_id(self,contact,*,skill_policy=None,session_kind='chat'):
        scope=self.scope(contact,skill_policy,session_kind)
        return self.store.get_session(scope) or 'new-'+scope

    def reset(self,contact,*,skill_policy=None,session_kind='chat'):
        scope=self.scope(contact,skill_policy,session_kind)
        with self.session_guard(contact,session_kind=session_kind),self._guard:
            self._drop(scope)
            self.store.set_session(scope,'')

    def _drop(self,scope):
        w=self.workers.pop(scope,None)
        if w:
            self._credentials.pop(w.credential,None)
            w.client.close()

    def close(self):
        with self._guard:
            for key in list(self.workers):
                self._drop(key)

    def alive(self,profile='default'):
        # No agent turn and no personal auth file contents are returned.
        return (self.cfg.codex_home_path()/'auth.json').is_file()

    def skills(self,contact=None):
        return self.tools.catalogue.list()

    def _error_detail(self,exc):
        detail=getattr(exc,'_butler_safe_detail',str(exc))
        for secret in [self.cfg.token,self.cfg.wxbot_token,*self._credentials.keys(),*self._credentials.values()]:
            if secret:detail=detail.replace(secret,'[REDACTED]')
        detail=re.sub(r'(?i)(bearer\s+)\S+',r'\1[REDACTED]',detail)
        detail=re.sub(r'\b(?:sk-[A-Za-z0-9_-]{16,}|eyJ[A-Za-z0-9_.-]{30,})\b','[REDACTED]',detail)
        detail=re.sub(r'(https?://)[^\s/@]+:[^\s/@]+@',r'\1[REDACTED]@',detail)
        return detail[:1000]

    def _options(self,workspace):
        return {
            'features':{'shell_tool':False,'unified_exec':False,'code_mode':False,
                        'code_mode_host':True,'apps':False,'plugins':False,'memories':False,
                        'browser_use':False,'computer_use':False,'view_image':False,
                        'skip_host_skill_discovery':True},
            'agents':{'enabled':False},'skills':{'bundled':{'enabled':False}},
            'web_search':'disabled','project_doc_max_bytes':0,
            'approval_policy':'never',
            'default_permissions':'butler',
            'permissions':{'butler':{'filesystem':{':root':'deny',str(workspace):'read'},
                                     'network':{'enabled':False}}},
            'mcp_servers':{'butler':{'url':f'http://127.0.0.1:{self.cfg.port}/mcp',
                'bearer_token_env_var':'BUTLER_TOOL_CAPABILITY','required':True,
                'default_tools_approval_mode':'approve',
                'tool_timeout_sec':30,'enabled_tools':list(__import__('butler.tools',fromlist=['TOOL_SCHEMAS']).TOOL_SCHEMAS)}}}

    def _workspace(self,scope,policy):
        workspace=self.cfg.data_path()/'workspaces'/scope
        skills=workspace/'skills'
        skills.mkdir(parents=True,exist_ok=True)
        source=self.tools.catalogue._entries()
        for name in [policy['role_skill'],*policy['allowed_skills']]:
            base=source[name]['_path'].parent
            target=skills/name
            for path in base.rglob('*'):
                if path.is_file() and path.suffix.lower() in ('.md','.txt') and path.resolve().is_relative_to(base.resolve()):
                    dest=target/path.relative_to(base)
                    dest.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copyfile(path,dest)
        return workspace

    def _worker(self,scope,policy,capability,contact_name='',deadline=None):
        with self._guard:
            deadline.check()
            for key,w in list(self.workers.items()):
                if not w.busy and time.monotonic()-w.used>self.cfg.codex_idle_seconds:
                    self._drop(key)
            if scope in self.workers:
                w=self.workers[scope]
                self._credentials[w.credential]=capability
                deadline.attach(w.client)
                deadline.check()
                w.busy=True
                return w
            idle=sorted((w.used,key) for key,w in self.workers.items() if not w.busy)
            if len(self.workers)+len(self._starting)>=self.cfg.codex_max_workers and idle:
                self._drop(idle[0][1])
            self._starting.add(scope)
        try:
            return self._initialize_worker(scope,policy,capability,contact_name,deadline)
        finally:
            with self._guard:self._starting.discard(scope)

    def _initialize_worker(self,scope,policy,capability,contact_name,deadline):
        from openai_codex import CodexConfig,ApprovalMode
        workspace=self._workspace(scope,policy)
        self.cfg.codex_home_path().mkdir(parents=True,exist_ok=True)
        credential=secrets.token_urlsafe(32)
        self._credentials[credential]=capability
        options=self._options(workspace)
        # Thread overrides and startup overrides both constrain tool discovery.
        from ..runtime_config import sdk_overrides
        environment={'CODEX_HOME':str(self.cfg.codex_home_path()),
             'BUTLER_TOOL_CAPABILITY':credential,
             'NO_PROXY':os.environ.get('NO_PROXY','')+',127.0.0.1,localhost,::1',
             'no_proxy':os.environ.get('no_proxy','')+',127.0.0.1,localhost,::1'}
        # Windows Internet Settings are visible to urllib but not reliably
        # inherited by the Rust SDK runtime. Pass only the resolved proxies.
        for protocol,value in getproxies().items():
            if protocol in ('http','https','all'):
                environment[protocol.upper()+'_PROXY']=value if '://' in value else 'http://'+value
        config=CodexConfig(cwd=str(workspace),env=environment,
             config_overrides=sdk_overrides(options))
        record('hermes_status','running',backend='codex',error_code='worker_initializing')
        self.store.event(contact_name,'model_initializing','started',backend='codex')
        from .codex_runtime import CallDeadline,DeadlineCodex
        startup=CallDeadline(min(60,deadline.remaining()))
        client=None
        try:
            if self.client_factory:
                client=self.client_factory(config)
                deadline.attach(client);startup.attach(client)
            else:
                client=DeadlineCodex(config,(deadline,startup))
            deadline.check();startup.check()
            from openai_codex.errors import InternalRpcError
            # account/read performs remote routing discovery with its own
            # short timeout. Keep the same transport warm while retrying
            # this read; no turn or business tool has been submitted yet.
            for attempt in range(1,4):
                try:
                    account=client.account()
                    deadline.check();startup.check()
                    break
                except InternalRpcError as exc:
                    if 'workspace routing discovery timed out' not in str(exc) or attempt==3:
                        raise
                    self.log('Codex 路由初始化超时，保留连接重试（%s/3），尚未提交消息',attempt)
                    record('hermes_status','running',backend='codex',error_code='routing_retry',attempt=attempt)
                    self.store.event(contact_name,'model_initializing','retrying',attempt=attempt)
            if not account.account:
                raise HermesError('Codex 未登录；请运行 python -m butler login')
            instructions=(
                'You are a WeChat conversational companion. Answer naturally in the user\'s language, '
                'like a real person, with length matched to the situation. '
                'Greetings, acknowledgements and simple questions: very short, a few words to one short sentence. '
                'Concrete questions: two or three sentences. '
                'Requests that need explanation or analysis: expand as appropriate. '
                'The supplied role skill is mandatory and overrides conflicting personas in history. '
                'Do not offer persona changes or deployment tutorials unless asked. '
                'Use only the supplied skills and Butler tools. Tool identity is server-owned. '
                'Never claim an action succeeded without its tool result. '
                'When a tool succeeds, confirm it in plain human words; never echo technical details to the user, '
                'such as task or reminder ids, "创建成功", or "操作完成". Tool results, including ids, are for your '
                'internal judgment only (for example, cancelling a reminder later). '
                'Do not output action markers. Return only the user-facing final answer; tool progress is logged separately.')
            kwargs={'cwd':str(workspace),'config':options,'approval_mode':ApprovalMode.deny_all,
                    'base_instructions':instructions,'developer_instructions':
                    'Mandatory role: '+policy['role_skill']+'. Read its required references using Butler skill_read.\n'
                    +self.tools.catalogue.read(policy['role_skill'])}
            if self.cfg.codex_model:
                kwargs['model']=self.cfg.codex_model
            thread_id=self.store.get_session(scope)
            if thread_id:
                from openai_codex.errors import InternalRpcError,InvalidRequestError
                try:thread=client.thread_resume(thread_id,**kwargs)
                except (InternalRpcError,InvalidRequestError) as exc:
                    detail=self._error_detail(exc)
                    self.log('Codex 会话恢复失败，尝试新建同身份会话：%s',detail)
                    thread=client.thread_start(**kwargs)
                    self.store.event(contact_name,'model_session','recovered',error_type=type(exc).__name__,error_detail=detail)
                    record('hermes_status','recovered',backend='codex',error_type=type(exc).__name__,error_code='thread_resume_failed')
            else:thread=client.thread_start(**kwargs)
            deadline.check();startup.check()
            self.store.set_session(scope,thread.id)
            w=Worker(client,thread,credential,time.monotonic(),True)
            with self._guard:
                deadline.check();startup.finish()
                self._starting.discard(scope)
                self.workers[scope]=w
            return w
        except BaseException as exc:
            # Capture redacted details before revoking the opaque worker token.
            if isinstance(exc,Exception):exc._butler_safe_detail=self._error_detail(exc)
            self._credentials.pop(credential,None)
            if client is not None:client.close()
            raise
        finally:
            startup.cancel()

    def chat(self,contact,text,*,extra_system='',timeout=None,skill_policy=None,session_kind='chat'):
        from openai_codex import SkillInput,TextInput
        policy=self.tools.catalogue.validate(skill_policy or DEFAULT_POLICY)
        scope=self.scope(contact,policy,session_kind)
        limit=timeout or self.cfg.codex_timeout
        self.store.identify(owner_key(contact),contact)
        with self.session_guard(contact,session_kind=session_kind):
            from .codex_runtime import CallDeadline
            worker=None;submitted=False;acquired=False
            deadline=CallDeadline(limit)
            try:
                acquired=self._slots.acquire(timeout=deadline.remaining())
                if not acquired:raise HermesError('Codex 请求队列等待超时')
                capability=self.tools.issue(owner=tool_owner_key(contact),memory_owner=owner_key(contact),contact=contact.name,
                    policy=policy,read_only=session_kind=='heartbeat',request_id=current_request_id() or uuid.uuid4().hex,
                    memory_allowed=contact.identity_status not in {'unknown','ambiguous','disabled','observed'},ttl=limit+60)
                worker=self._worker(scope,policy,capability,contact.name,deadline)
                workspace=self.cfg.data_path()/'workspaces'/scope
                inputs=[TextInput(text=contact.identity(backend='codex')+'\n'+extra_system+'\n'+text)]
                for name in [policy['role_skill'],*policy['allowed_skills']]:
                    inputs.append(SkillInput(name=name,path=str(workspace/'skills'/name/'SKILL.md')))
                record('hermes_request','started',backend='codex',session_id=worker.thread.id)
                self.store.event(contact.name,'model_request','started',backend='codex',thread_id=worker.thread.id)
                deadline.check()
                # Mark before the call: an RPC failure may occur after submission.
                submitted=True
                turn=worker.thread.turn(inputs)
                final=None; completed=False
                for event in turn.stream():
                    payload=event.payload
                    if hasattr(payload,'model_dump'):
                        payload=payload.model_dump(mode='json',by_alias=True)
                    if not isinstance(payload,dict):
                        continue
                    if event.method in ('item/started','item/completed'):
                        item=payload.get('item') or {}
                        kind=item.get('type')
                        # MCP progress comes from ToolService, with the original
                        # request id, avoiding duplicate SDK and HTTP event rows.
                        if kind=='dynamicToolCall':
                            status='running' if event.method=='item/started' else 'completed'
                            name=item.get('tool','tool')
                            record('hermes_tool',status,backend='codex',tool=name)
                            self.store.event(contact.name,'model_tool',status,tool=name)
                        if event.method=='item/completed' and kind=='agentMessage' and item.get('phase') in (None,'final_answer'):
                            final=item.get('text')
                    if event.method=='turn/completed':
                        completed=(payload.get('turn') or {}).get('status')=='completed'
                deadline.check()
                if not completed or not isinstance(final,str) or not final.strip():
                    raise HermesError('Codex 超时、失败或回复不完整，未提交微信发送')
                record('hermes_result','ok',backend='codex',characters=len(final))
                self.store.event(contact.name,'model_result','ok',characters=len(final))
                return final.strip()
            except Exception as exc:
                if deadline.expired:exc=TimeoutError('Codex 请求超时（包括初始化），已关闭运行连接')
                detail=self._error_detail(exc)
                self.last_error=detail
                self.log('Codex 调用失败（%s）：%s','提交后' if submitted else '提交前',detail)
                with self._guard:
                    self._drop(scope)
                record('hermes_result','error',backend='codex',error_type=type(exc).__name__,
                       error_code='after_submission' if submitted else 'before_submission')
                self.store.event(contact.name,'model_result','error',error_type=type(exc).__name__,
                                 error_detail=detail,retry_safe=not submitted)
                failure=HermesError('Codex 调用失败：'+type(exc).__name__+'：'+detail,
                                    status=getattr(exc,'status',0),detail=detail)
                failure.retry_safe=not submitted
                raise failure from exc
            finally:
                deadline.cancel()
                if worker:
                    worker.busy=False; worker.used=time.monotonic()
                    self._credentials.pop(worker.credential,None)
                if acquired:self._slots.release()
