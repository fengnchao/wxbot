"""Server-issued identity capabilities and the single business tool boundary."""
import base64
import hashlib
import hmac
import json
import secrets
import time


READ_TOOLS = {'skills_list','skill_read','memory_get','memory_search','reminder_list','telegram_relay_status'}
TOOL_SCHEMAS = {
    'skills_list': ('List skills permitted for this identity', {}),
    'skill_read': ('Read an allowed skill or a relative reference file', {'name':{'type':'string'},'file_path':{'type':'string'}}),
    'memory_get': ('Read this identity\'s saved notes', {}),
    'memory_search': ('Search this identity\'s saved notes', {'query':{'type':'string'}}),
    'memory_set': ('Save an explicitly confirmed fact or preference for this identity', {'key':{'type':'string'},'value':{'type':'string'}}),
    'memory_delete': ('Forget an explicitly requested saved fact for this identity', {'key':{'type':'string'}}),
    'reminder_create': ('Create a reminder; schedule is in 2m, ISO datetime, or 5-field cron', {'text':{'type':'string'},'schedule':{'type':'string'}}),
    'reminder_list': ('List reminders owned by this identity', {}),
    'reminder_cancel': ('Cancel a reminder owned by this identity', {'id':{'type':'string'}}),
    'telegram_relay_status': ('Read configured Telegram relay and runtime status (administrators only)', {}),
    'telegram_relay_pause': ('Pause the configured Telegram relay (administrators only)', {}),
    'telegram_relay_resume': ('Resume the configured Telegram relay (administrators only)', {}),
}
REQUIRED_ARGUMENTS = {
    'skill_read':('name',),'memory_set':('key','value'),'memory_delete':('key',),
    'reminder_create':('text','schedule'),'reminder_cancel':('id',),
}


class ToolService:
    def __init__(self, store, catalogue, *, secret=None, policy_loader=None, event_sink=None):
        self.store, self.catalogue = store, catalogue
        self.secret = secret or secrets.token_bytes(32)
        self.policy_loader = policy_loader
        self.event_sink = event_sink
        self.relay_settings = None

    def _relay_admin(self, context):
        if self.relay_settings is None:
            return False
        try:
            return context['contact'] in self.relay_settings.read()['admin_contacts']
        except (OSError, ValueError):
            return False

    def issue(self, *, owner, contact, policy, read_only=False, request_id, ttl=900, memory_allowed=True,memory_owner=None):
        policy=self.catalogue.validate(policy)
        payload={'owner':owner,'memory_owner':memory_owner if memory_owner is not None else owner,
                 'contact':contact,'policy':policy,'read_only':bool(read_only),'memory_allowed':bool(memory_allowed),
                 'request_id':request_id,'expires':time.time()+ttl}
        encoded=base64.urlsafe_b64encode(json.dumps(payload,separators=(',',':'),ensure_ascii=False).encode()).decode().rstrip('=')
        sig=hmac.new(self.secret,encoded.encode(),hashlib.sha256).hexdigest()
        return encoded+'.'+sig

    def verify(self, token):
        try:
            token=getattr(self,'worker_credentials',{}).get(token,token)
            encoded,sig=token.rsplit('.',1)
            expected=hmac.new(self.secret,encoded.encode(),hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected,sig):
                raise ValueError('signature')
            context=json.loads(base64.urlsafe_b64decode(encoded+'='*(-len(encoded)%4)))
            if context['expires']<=time.time():
                raise ValueError('expired')
            self.catalogue.validate(context['policy'])
            if self.policy_loader:
                current=self.policy_loader(context['contact'])
                if current is None or self.catalogue.validate(current)!=context['policy']:
                    raise ValueError('policy changed')
            return context
        except Exception:
            raise PermissionError('Invalid, expired, or revoked tool capability') from None

    def definitions(self, token):
        c=self.verify(token)
        names=self.catalogue.allowed_tools(c['policy']) | {'skills_list','skill_read'}
        if not c.get('memory_allowed',True):
            names={name for name in names if not name.startswith('memory_')}
        if c['read_only']:
            names &= READ_TOOLS
        if not self._relay_admin(c):
            names = {name for name in names if not name.startswith('telegram_relay_')}
        return [{'name':n,'description':TOOL_SCHEMAS[n][0],
                 'inputSchema':{'type':'object','properties':TOOL_SCHEMAS[n][1],
                                'required':list(REQUIRED_ARGUMENTS.get(n,())), 'additionalProperties':False},
                 'annotations':{'readOnlyHint':n in READ_TOOLS,'destructiveHint':False,
                                'idempotentHint':n in READ_TOOLS or n in ('memory_set','reminder_cancel'),
                                'openWorldHint':False}}
                for n in sorted(names & TOOL_SCHEMAS.keys())]

    def call(self, name, args, token, call_id):
        c=self.verify(token)
        def emit(status):
            self.store.event(c['contact'],'model_tool',status,tool=name,request_id=c['request_id'])
            if self.event_sink:
                self.event_sink(c['contact'],c['request_id'],'hermes_tool',status,backend='codex',tool=name)
        emit('running')
        try:
            result=self._call(name,args,token,call_id)
            emit('completed')
            return result
        except Exception:
            emit('failed')
            raise

    def _call(self, name, args, token, call_id):
        c=self.verify(token)
        if not isinstance(args,dict) or any(k in args for k in ('owner','contact','uid','user_id','profile')):
            raise PermissionError('Tool identity is supplied by the server')
        if name not in {d['name'] for d in self.definitions(token)}:
            raise PermissionError('Tool not permitted for this request')
        if set(args)-set(TOOL_SCHEMAS[name][1]):
            raise ValueError('Unknown tool arguments')
        for key,value in args.items():
            if not isinstance(value,str) or len(value)>10000:
                raise ValueError('Tool arguments must be bounded strings')
        required=REQUIRED_ARGUMENTS.get(name,())
        if any(not args.get(key) for key in required):
            raise ValueError('Missing required tool argument')
        if name.startswith('telegram_relay_') and name not in READ_TOOLS and not call_id:
            raise ValueError('Write tools require a call id')
        if name=='skills_list':
            allowed={c['policy']['role_skill'],*c['policy']['allowed_skills']}
            return {'items':[s for s in self.catalogue.list() if s['name'] in allowed]}
        if name=='skill_read':
            if args.get('name') not in {c['policy']['role_skill'],*c['policy']['allowed_skills']}:
                raise PermissionError('Skill not permitted')
            return {'text':self.catalogue.read(args['name'],args.get('file_path','SKILL.md'))}
        owner=c['owner']
        memory_owner=c.get('memory_owner',owner)
        with self.store.transaction() as db:
            fingerprint=hashlib.sha256(json.dumps([name,args],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            old=db.execute('SELECT fingerprint,result FROM operations WHERE owner=? AND request_id=? AND call_id=?',
                           (owner,c['request_id'],str(call_id))).fetchone()
            if old:
                if old['fingerprint']!=fingerprint:
                    raise ValueError('Tool call id reused with different arguments')
                return json.loads(old['result'])
            if name=='reminder_create':
                duplicate=db.execute('SELECT result FROM operations WHERE owner=? AND request_id=? AND fingerprint=? LIMIT 1',
                                     (owner,c['request_id'],fingerprint)).fetchone()
                if duplicate:
                    db.execute('INSERT INTO operations VALUES(?,?,?,?,?)',
                               (owner,c['request_id'],str(call_id),fingerprint,duplicate['result']))
                    return json.loads(duplicate['result'])
            if name.startswith('telegram_relay_'):
                # Re-read the separate global-admin allowlist for every call, including retries.
                if not self._relay_admin(c):
                    raise PermissionError('Relay administrator permission required')
                if name == 'telegram_relay_status':
                    result = self.relay_settings.status()
                else:
                    snapshot = self.relay_settings.read()
                    if c['contact'] not in snapshot['admin_contacts']:
                        raise PermissionError('Relay administrator permission required')
                    result = self.relay_settings.update({'enabled': name == 'telegram_relay_resume'}, snapshot['version'])
            elif name in ('memory_get','memory_search'):
                result={'items':self.store.memories(memory_owner,args.get('query',''),db=db)}
            elif name=='memory_set':
                result=self.store.set_memory(memory_owner,args.get('key'),args.get('value'),db=db)
            elif name=='memory_delete':
                result=self.store.delete_memory(memory_owner,args.get('key'),db=db)
            elif name=='reminder_list':
                result={'items':self.store.reminders(owner,db=db)}
            elif name=='reminder_create':
                result=self.store.create_reminder(owner,c['contact'],args.get('text'),args.get('schedule'),db=db)
            elif name=='reminder_cancel':
                result=self.store.cancel_reminder(owner,args.get('id'),db=db)
            else:
                raise ValueError('Unknown tool')
            if name not in READ_TOOLS:
                if not call_id:
                    raise ValueError('Write tools require a call id')
                db.execute('INSERT INTO operations VALUES(?,?,?,?,?)',(owner,c['request_id'],str(call_id),fingerprint,json.dumps(result)))
            return result
