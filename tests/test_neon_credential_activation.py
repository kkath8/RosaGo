"""Offline guard tests using synthetic verifier strings. No DPAPI or network."""
import ast
from copy import deepcopy
from unittest.mock import Mock,patch
import unittest

from pglast import parse_sql
from pglast.stream import RawStream
from tools import activate_neon_evaluation_credential as activation

SYNTHETIC=b'SCRAM-SHA-256$4096:c2FsdA==$a2V5:a2V5'


class NeonCredentialActivation(unittest.TestCase):
    def test_only_runtime_login_diff_is_allowed(self):
        before=dict(roles=[dict(rolname='rosago_session_app',rolcanlogin=False,rolsuper=False),
                           dict(rolname='rosago_session_owner',rolcanlogin=False,rolsuper=False)],
                    policy='original',grants=['SELECT'])
        preserved=deepcopy(before);after=activation.expected_active(before)
        self.assertEqual(before,preserved)
        self.assertTrue(after['roles'][0]['rolcanlogin'])
        self.assertFalse(after['roles'][1]['rolcanlogin'])
        after['roles'][0]['rolcanlogin']=False
        self.assertEqual(after,before)

    def test_already_active_baseline_rejected(self):
        with self.assertRaisesRegex(activation.setup.Stop,'nologin_baseline_mismatch'):
            activation.expected_active(dict(roles=[dict(rolname='rosago_session_app',rolcanlogin=True)]))

    def test_execution_copy_changes_only_two_approved_stops(self):
        text=activation.REVIEW.read_text()
        body=activation.approved_body(text,None,SYNTHETIC)
        original=[r.stmt for r in parse_sql(text)];approved=[r.stmt for r in parse_sql(body)]
        self.assertEqual(len(approved),len(original)-1) # Commit delayed until verification.
        self.assertEqual(type(approved[0]).__name__,'TransactionStmt')
        self.assertEqual(type(approved[1]).__name__,'DoStmt')
        self.assertEqual(RawStream()(approved[2]),RawStream()(original[2]))
        self.assertEqual(RawStream()(approved[4]),RawStream()(original[4]))
        self.assertEqual(RawStream()(approved[5]),RawStream()(original[5]))
        alter=[n for n in approved if type(n).__name__=='AlterRoleStmt']
        self.assertEqual([n.role.rolename for n in alter],['rosago_session_app']*2)
        self.assertEqual([n.options[0].defname for n in alter],['password','canlogin'])
        self.assertEqual(activation.REVIEW.read_text(),text)

    def test_plaintext_or_invalid_verifier_rejected_safely(self):
        for invalid in (b'fake-test-secret',b'md5bad',b"SCRAM-SHA-256$bad';"):
            with self.subTest(kind=len(invalid)):
                with self.assertRaises(activation.setup.Stop) as result:
                    activation.approved_body(activation.REVIEW.read_text(),None,invalid)
                self.assertNotIn(invalid.decode(),str(result.exception))

    def test_removed_private_assignment_gate_rejected(self):
        text=activation.REVIEW.read_text().replace(activation.ASSIGNMENT,'')
        with self.assertRaisesRegex(activation.setup.Stop,'reviewed_activation_structure_mismatch'):
            activation.approved_body(text,None,SYNTHETIC)

    def test_all_static_sql_parses_without_execution(self):
        tree=ast.parse(activation.ROOT.joinpath('tools/activate_neon_evaluation_credential.py').read_text())
        count=0
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='execute':
                if node.args and isinstance(node.args[0],ast.Constant) and isinstance(node.args[0].value,str):
                    parse_sql(node.args[0].value);count+=1
        self.assertGreater(count,10)

    def test_tls_or_password_auth_failure_denies_before_sql_verifier(self):
        for tls,used in ((False,True),(True,False)):
            conn=Mock();conn.pgconn.ssl_in_use=tls;conn.pgconn.used_password=used
            conn.__enter__=Mock(return_value=conn);conn.__exit__=Mock(return_value=False)
            with patch.object(activation.psycopg,'connect',return_value=conn),patch.object(activation,'_verify_pool') as verifier:
                with self.assertRaisesRegex(activation.setup.Stop,'runtime_tls_or_password_auth_missing'):
                    activation.verify_runtime(dict(host='example.invalid'),b'synthetic-only')
                verifier.assert_not_called()


if __name__=='__main__':unittest.main()
