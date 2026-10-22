"""Authenticated stateless Streamable HTTP MCP: JSON responses, no SSE sessions."""
import json


def dispatch(service,body,credential):
    service.verify(credential)
    if not isinstance(body,dict) or body.get('jsonrpc')!='2.0':
        raise ValueError('Invalid MCP JSON-RPC request')
    method=body.get('method'); rid=body.get('id')
    params=body.get('params') or {}
    if not isinstance(params,dict):
        raise ValueError('Invalid MCP params')
    if rid is None and method in ('notifications/initialized','notifications/cancelled'):
        return None
    if method=='initialize':
        result={'protocolVersion':params.get('protocolVersion','2025-03-26'),
                'capabilities':{'tools':{}},'serverInfo':{'name':'butler-wechat','version':'1.0.0'}}
    elif method=='ping':
        result={}
    elif method=='tools/list':
        result={'tools':service.definitions(credential)}
    elif method=='tools/call':
        try:
            value=service.call(params.get('name'),params.get('arguments') or {},credential,str(rid))
            result={'content':[{'type':'text','text':json.dumps(value,ensure_ascii=False)}],'isError':False}
        except (ValueError,PermissionError) as exc:
            result={'content':[{'type':'text','text':str(exc)}],'isError':True}
    else:
        return {'jsonrpc':'2.0','id':rid,'error':{'code':-32601,'message':'Method not found'}}
    return {'jsonrpc':'2.0','id':rid,'result':result}
