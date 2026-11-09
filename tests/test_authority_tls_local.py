"""Real loopback TLS verification; ephemeral CA, no OS trust or hosted access."""
from datetime import datetime,timedelta,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import ssl
import tempfile
from threading import Thread
import unittest

from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import httpx
from authority_http_transport import AuthorityHTTPTransport
from session_realms import SessionStorageUnavailable

class LocalTLSTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='rosago-authority-tls-')
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'localhost')])
        now=datetime.now(timezone.utc)
        cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1))
            .not_valid_after(now+timedelta(hours=1)).add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost')]),critical=False)
            .add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True).sign(key,hashes.SHA256()))
        cls.cert=Path(cls.temp.name)/'cert.pem';private=Path(cls.temp.name)/'key.pem'
        cls.cert.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        private.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                raw=b'{"local_tls_verified":true}'
                self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cls.cert,private)
        cls.server.socket=context.wrap_socket(cls.server.socket,server_side=True)
        cls.thread=Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=2);cls.temp.cleanup()

    def transport(self,host,*,trust=False):
        # Custom ports are restricted to explicit loopback tests, even with TLS.
        def factory(**options):
            return httpx.Client(verify=ssl.create_default_context(cafile=str(self.cert)) if trust else True,**options)
        client=AuthorityHTTPTransport(f'https://{host}:{self.server.server_port}/v1/authority',
            'synthetic-'+ 'x'*40,client_factory=factory,local_test=True)
        self.addCleanup(client.close);return client

    def test_trusted_certificate_and_exact_hostname_succeed(self):
        self.assertEqual(self.transport('localhost',trust=True).exchange({}),{'local_tls_verified':True})

    def test_untrusted_certificate_or_wrong_hostname_fails_closed(self):
        for host,trust in [('localhost',False),('127.0.0.1',True)]:
            with self.assertRaises(SessionStorageUnavailable):self.transport(host,trust=trust).exchange({})
