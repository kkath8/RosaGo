"""Synthetic local fixture only: actual Worker in separate local workerd process.

Loopback HTTP exposes the metadata protocol with a random test credential. It
does not establish hosted Cloudflare durability or TLS/provider qualification.
"""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import subprocess
from threading import Lock,Thread

from authority_http_transport import AuthorityHTTPTransport
from protected_session_authority import AuthorityBinding,ProtectedRevisionAuthority

ROOT=Path(__file__).resolve().parents[1]


class IndependentAuthorityFixture:
    def __init__(self,path,namespace):
        self.path,self.namespace=path,namespace
        self.binding=AuthorityBinding(secrets.token_hex(16),secrets.token_hex(16),0)
        self.token=secrets.token_hex(24);self.lock=Lock();self.clients=[];self.start()
        self.control('initialize',config={'authority_id':self.binding.authority_id,
            'incarnation':self.binding.incarnation,'namespace':namespace,
            'epochs':{'user':'user_epoch','admin':'admin_epoch'}})
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                try:
                    self.connection.settimeout(.5)
                    if self.path!='/v1/authority' or self.headers.get('Authorization')!='Bearer '+owner.token:
                        self.send_error(403);return
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=65536:self.send_error(400);return
                    request=json.loads(self.rfile.read(size))
                    if 'test_control' in request:self.send_error(403);return
                    raw=json.dumps(owner.exchange(request)).encode()
                    self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
                except Exception:
                    self.send_error(503)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)+'/v1/authority'

    def start(self):
        self.process=subprocess.Popen(['node',str(ROOT/'evaluation/infrastructure/authority/test/stdio-workerd-service.mjs'),
            str(self.path),self.binding.authority_id,self.binding.incarnation],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
        if json.loads(self.process.stdout.readline())!={'fixture_ready':True}:
            raise RuntimeError('Local workerd fixture did not become ready.')

    def exchange(self,request):
        with self.lock:
            self.process.stdin.write(json.dumps(request)+'\n');self.process.stdin.flush()
            line=self.process.stdout.readline()
            if not line:raise RuntimeError('Local authority stopped.')
            return json.loads(line)

    def control(self,operation,**arguments):
        return self.exchange({'test_control':operation,**arguments})

    def restart(self):
        with self.lock:
            self.process.stdin.close();self.process.wait(timeout=8);self.process.stdout.close();self.start()

    def client(self):
        transport=AuthorityHTTPTransport(self.url,self.token,local_test=True);self.clients.append(transport)
        return ProtectedRevisionAuthority(transport,self.binding,response_budget=1.5)

    def close(self):
        for client in self.clients:client.close()
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)
        self.process.stdin.close();self.process.wait(timeout=8);self.process.stdout.close()
