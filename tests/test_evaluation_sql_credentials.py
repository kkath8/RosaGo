import unittest
from unittest.mock import patch
from evaluation_sql_credentials import validate_evaluation_sql_credential,PROJECT

class CredentialTests(unittest.TestCase):
    def dsn(self,**replace):
        values={'host':'db.'+PROJECT+'.supabase.co','user':'rosago_data_gateway','dbname':'postgres',
            'password':'synthetic-'+ 'x'*40,'sslmode':'verify-full','sslrootcert':'system','port':'5432'}
        values.update(replace)
        from psycopg.conninfo import make_conninfo
        return make_conninfo(**values)
    def test_offline_bound_role_project_tls_and_redacted_repr(self):
        with patch('socket.socket.connect',side_effect=AssertionError('Network forbidden')):
            credential=validate_evaluation_sql_credential(self.dsn(),role='rosago_data_gateway')
            self.assertEqual(credential.project,PROJECT)
            self.assertNotIn('synthetic-',repr(credential))
            pooled=self.dsn(host='aws-0-ap-southeast-1.pooler.supabase.com',user='rosago_data_gateway.'+PROJECT)
            self.assertEqual(validate_evaluation_sql_credential(pooled,role='rosago_data_gateway').role,'rosago_data_gateway')
    def test_forbids_target_tls_role_and_connection_overrides(self):
        for replacement in ({'host':'db.otherproject.supabase.co'}, {'user':'postgres'}, {'sslmode':'require'},
            {'sslmode':'disable'}, {'sslrootcert':''}, {'hostaddr':'127.0.0.1'}, {'options':'-c role=postgres'},
            {'port':'6543'}, {'connect_timeout':'0'}, {'password':'short'},
            {'host':'aws-0-ap-southeast-1.pooler.supabase.com','user':'rosago_data_gateway.otherproject'}):
            with self.subTest(replacement=list(replacement)):
                with self.assertRaises(ValueError) as error:validate_evaluation_sql_credential(self.dsn(**replacement),role='rosago_data_gateway')
                self.assertNotIn('synthetic-',str(error.exception))
