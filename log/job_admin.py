"""Local dashboard-to-Butler administrative deletion proxy."""
import json
from urllib.error import HTTPError
from urllib.request import Request,build_opener,ProxyHandler

from butler.job_admin import validate_delete_payload
from .user_admin import _NoRedirect


def request_job_delete(config,payload):
    validate_delete_payload(payload)
    if (config.get('_connection') or {}).get('mode','local')!='local':
        return 503,{'error':'此任务请到对端管理台删除'}
    server=config.get('server') or {}
    token=str(server.get('token') or '')
    if not token:return 503,{'error':'Butler 管理凭据未配置'}
    request=Request('http://127.0.0.1:'+str(int(server.get('port') or 8770))+'/v1/jobs/delete',
        data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    try:
        try:response=build_opener(ProxyHandler({}),_NoRedirect()).open(request,timeout=15)
        except HTTPError as exc:response=exc
        with response:
            result=json.loads(response.read(1<<20).decode('utf-8'))
            if not isinstance(result,dict):raise ValueError('Invalid Butler result')
            # Never echo the service credential, even if an upstream error does.
            def scrub(value):
                if isinstance(value,str):return value.replace(token,'[redacted]')
                if isinstance(value,dict):return {key:scrub(item) for key,item in value.items() if key.lower() not in {'token','authorization'}}
                if isinstance(value,list):return [scrub(item) for item in value]
                return value
            return response.status,scrub(result)
    except Exception as exc:
        return 503,{'error':'任务删除请求暂不可用（'+type(exc).__name__+'），请刷新确认任务状态'}
