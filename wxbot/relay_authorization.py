"""Short-lived relay permission snapshots; UI callers never perform HTTP work."""
from collections import deque
import ipaddress
import json
import math
import threading
import time
from urllib.parse import urlsplit, urlunsplit

from .log import log

TTL_SECONDS = .5
RETRY_SECONDS = .5
MAX_RESPONSE = 4096
MAX_CONTACTS = 512


def _local_endpoint(url):
    """Pin localhost to a numeric address and reject caller-controlled URL parts."""
    try:
        if not isinstance(url,str) or url != url.strip():
            return None
        parts=urlsplit(url)
        if (parts.scheme not in {'http','https'} or parts.username is not None or
                parts.password is not None or parts.query or parts.fragment or parts.path not in {'','/'}):
            return None
        host=parts.hostname
        if host=='localhost':
            host='127.0.0.1'
        if not host or '%' in host or not ipaddress.ip_address(host).is_loopback:
            return None
        port=parts.port
        if port is not None and not 1<=port<=65535:
            return None
        netloc=('['+host+']') if ':' in host else host
        if port is not None:
            netloc+=':'+str(port)
        return urlunsplit((parts.scheme,netloc,'/v1/telegram-relay/authorize','',''))
    except (ValueError,TypeError):
        return None


class RelayAuthorization:
    def __init__(self,url,token,*,clock=time.monotonic,session_factory=None):
        self.clock=clock
        self._endpoint=_local_endpoint(url)
        self._token=token if isinstance(token,str) and token.strip() and '\r' not in token and '\n' not in token else ''
        self._session_factory=session_factory
        self._condition=threading.Condition()
        self._queue=deque()
        self._inflight=set()
        self._cache={}
        self._next_attempt={}
        self._closed=False
        self._last_warning=-math.inf
        self._thread=None
        if self._endpoint and self._token:
            self._thread=threading.Thread(target=self._run,name='wxbot-relay-authorization',daemon=True)
            self._thread.start()

    def allowed(self,delivery):
        if not getattr(delivery,'package_id',None):
            return True
        contact=getattr(delivery,'contact',None)
        if not isinstance(contact,str) or not contact.strip() or len(contact)>256:
            return None
        now=self.clock()
        with self._condition:
            if self._closed or self._thread is None:
                return None
            cached=self._cache.get(contact)
            if cached is not None and 0<=now-cached[1]<=TTL_SECONDS:
                return cached[0]
            self._cache.pop(contact,None)
            if (contact not in self._inflight and now>=self._next_attempt.get(contact,-math.inf)
                    and len(self._inflight)<MAX_CONTACTS):
                self._inflight.add(contact)
                self._queue.append(contact)
                self._condition.notify()
            return None

    def _warn(self,reason):
        # Fixed categories only: do not include contact, token, URL or exception text.
        now=self.clock()
        if now-self._last_warning>=60:
            self._last_warning=now
            log.warning('[Telegram relay] 授权校验暂不可用（%s），保持暂停',reason)

    def _fetch(self,session,contact,started):
        response=None
        try:
            response=session.get(self._endpoint,params={'contact':contact},
                headers={'Authorization':'Bearer '+self._token},timeout=(.25,.4),
                allow_redirects=False,stream=True)
            if response.status_code!=200:
                self._warn('http_status')
                return None
            data=bytearray()
            for chunk in response.iter_content(1024):
                data.extend(chunk)
                if len(data)>MAX_RESPONSE or self.clock()-started>TTL_SECONDS:
                    self._warn('response_limit')
                    return None
            result=json.loads(bytes(data).decode('utf-8'))
            if (not isinstance(result,dict) or set(result)!={'contact','allowed'} or
                    result['contact']!=contact or type(result['allowed']) is not bool):
                self._warn('invalid_receipt')
                return None
            return result['allowed']
        except Exception:
            self._warn('network_error')
            return None
        finally:
            if response is not None:
                try:response.close()
                except Exception:pass

    def _run(self):
        session=None
        try:
            while True:
                with self._condition:
                    while not self._queue and not self._closed:
                        self._condition.wait()
                    if self._closed:
                        return
                    contact=self._queue.popleft()
                started=self.clock()
                answer=None
                try:
                    if session is None:
                        if self._session_factory is None:
                            import requests
                            session=requests.Session()
                        else:
                            session=self._session_factory()
                        session.trust_env=False
                    answer=self._fetch(session,contact,started)
                except Exception:
                    self._warn('client_error')
                    session=None
                with self._condition:
                    now=self.clock()
                    self._inflight.discard(contact)
                    # Measure from request start so slow responses cannot revive
                    # an already stale grant as a fresh half-second permission.
                    if not self._closed and type(answer) is bool and 0<=now-started<=TTL_SECONDS:
                        self._cache[contact]=(answer,started)
                    else:
                        self._cache.pop(contact,None)
                    self._next_attempt[contact]=now+(0 if type(answer) is bool else RETRY_SECONDS)
                    if len(self._next_attempt)>MAX_CONTACTS:
                        oldest=next(iter(self._next_attempt))
                        self._next_attempt.pop(oldest,None)
                        self._cache.pop(oldest,None)
        finally:
            if session is not None:
                try:session.close()
                except Exception:pass

    def close(self):
        with self._condition:
            self._closed=True
            self._cache.clear()
            self._queue.clear()
            self._condition.notify_all()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=1)
