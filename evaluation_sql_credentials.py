"""Offline credential validation for proposed evaluation SQL roles only.

No environment loading, connection, password generation, or startup bypass.
Use a certificate-verifying libpq connection only after separate approval.
"""
from dataclasses import dataclass
import re
from psycopg.conninfo import conninfo_to_dict,make_conninfo

PROJECT='jfaufpfzfhysqkhcdsrs'
ROLES=frozenset(('rosago_session_app','rosago_data_gateway'))

@dataclass(frozen=True,repr=False)
class EvaluationSQLCredential:
    conninfo: str
    role: str
    project: str=PROJECT

def validate_evaluation_sql_credential(conninfo,*,role):
    try:
        if role not in ROLES or type(conninfo) is not str:raise ValueError()
        values=conninfo_to_dict(conninfo)
        if set(values)-{'host','port','dbname','user','password','sslmode','sslrootcert','connect_timeout','application_name'}:raise ValueError()
        host=values.get('host','')
        direct=host=='db.'+PROJECT+'.supabase.co'
        pooled=re.fullmatch(r'aws-[0-9]+-[a-z0-9-]+\.pooler\.supabase\.com',host) is not None
        if not direct and not pooled:raise ValueError()
        expected_user=role if direct else role+'.'+PROJECT
        if (values.get('user')!=expected_user or values.get('dbname')!='postgres'
                or values.get('port','5432')!='5432' or values.get('sslmode')!='verify-full'
                or values.get('sslrootcert')!='system' or not 32<=len(values.get('password',''))<=256
                or values.get('connect_timeout','2') not in ('1','2')):raise ValueError()
        values['connect_timeout']='2'
        return EvaluationSQLCredential(make_conninfo(**values),role)
    except Exception:
        raise ValueError('Evaluation SQL credentials require the approved project/role, verified TLS and bounded connection settings.') from None
