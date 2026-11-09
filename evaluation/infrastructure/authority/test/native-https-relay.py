"""Test-only TLS byte transport to actual local workerd via a private file relay.

Runs in a second cached container sharing the network-none DB namespace. No
host or public ports, no external route. Implements no authority decisions.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import secrets
import ssl
import time

ROOT=Path('/fixture')
keys=json.loads((ROOT/'secrets.json').read_text())
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_HEAD(self):
        operation=self.path.removeprefix('/v1/provider/')
        token=keys['revoke' if operation in ('revoke','constrain') else 'check']
        if operation not in ('check','inspect','revoke','constrain') or self.headers.get('Authorization')!='Bearer '+token:
            self.send_response(403);self.end_headers();return
        mode=(ROOT/'mode').read_text().strip()
        if mode=='redirect':
            self.send_response(307);self.send_header('Location','https://localhost/redirect-target');self.end_headers();return
        if mode=='outage':
            self.send_response(503);self.end_headers();return
        if mode=='timeout': time.sleep(1.2)
        name=secrets.token_hex(12)
        pending=ROOT/(name+'.request')
        try:
            request=json.loads(self.headers['X-RosaGo-Request'])
            part=ROOT/(name+'.part');part.write_text(json.dumps(dict(operation=operation,request=request,head=True)))
            part.replace(pending)
            answer=ROOT/(name+'.response');deadline=time.monotonic()+.8
            while not answer.exists():
                if time.monotonic()>deadline: raise TimeoutError()
                time.sleep(.005)
            reply=json.loads(answer.read_text());answer.unlink()
            if reply.get('status')!=200: raise ValueError()
            value=reply['value']
            if mode=='wrong-nonce': value['nonce']='wrong'
            raw=json.dumps(value) if mode!='malformed' else 'invalid-json'
            self.send_response(200);self.send_header('X-RosaGo-Result',raw)
            if mode=='duplicate': self.send_header('X-RosaGo-Result',raw)
            self.send_header('Cache-Control','no-store');self.end_headers()
        except Exception:
            self.send_response(503);self.end_headers()

server=ThreadingHTTPServer(('127.0.0.1',443),Handler)
context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(str(ROOT/'server.pem'),str(ROOT/'server.key'))
server.socket=context.wrap_socket(server.socket,server_side=True)
(ROOT/'tls-ready').write_text('ready')
server.serve_forever()
