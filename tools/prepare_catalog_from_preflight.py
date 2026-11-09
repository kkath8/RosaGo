"""Validate owner-operated schema evidence and bind review SQL; no database I/O."""
from collections import Counter
import hashlib
from pathlib import Path

from pglast import parse_sql, ast
from pglast.stream import RawStream
from tools.local_destination_catalog import FIELDS, read_json, require, timestamp, write_new

ROOT=Path(__file__).resolve().parents[1]
TARGET='brnkigrrqdrywahvcbvc'
TARGETS={
    'rosago_admin_mutate_destination_unlogged':'399faf695b6a607f33bf1fb7c2dd9386',
    'rosago_admin_mutate_destination':'4cab3fdc6baf75133fd19b8f1dde6345',
    'rosago_itinerary_interests_valid':'23e804b7aaad0adeff4ecd1db8e1a645',
}


def constraint_semantics(definition):
    """Local clone comparison only: ignore locations and associative AND nesting.

    Production SQL still pins the exact exported pg_get_constraintdef hash.
    PostgreSQL can flatten nested AND nodes when exported DDL is reparsed.
    """
    import json
    from pglast.parser import parse_sql_json
    tree=json.loads(parse_sql_json('ALTER TABLE public.places ADD CONSTRAINT review_probe '+definition+';'))
    def clean(value):
        if isinstance(value,list):return [clean(item) for item in value]
        if not isinstance(value,dict):return value
        result={key:clean(item) for key,item in value.items()
                if key not in ('location','stmt_location','stmt_len','list_start','list_end')}
        if 'BoolExpr' in result and result['BoolExpr'].get('boolop')=='AND_EXPR':
            expr=result['BoolExpr'];args=[]
            for item in expr.get('args',[]):
                if isinstance(item,dict) and item.get('BoolExpr',{}).get('boolop')=='AND_EXPR':args.extend(item['BoolExpr']['args'])
                else:args.append(item)
            expr['args']=args
        return result
    return clean(tree)


def function_body(function):
    statements=parse_sql(function['definition'])
    require(len(statements)==1 and isinstance(statements[0].stmt,ast.CreateFunctionStmt), 'Unexpected function definition.')
    statement=statements[0].stmt
    name='.'.join(part.sval for part in statement.funcname)
    require(name.startswith('public.rosago_') and name.split('.')[-1]==function['identity'].split('(')[0].split('.')[-1], 'Function identity mismatch.')
    identity=function['identity']
    if not identity.startswith('public.'):identity='public.'+identity
    signature=parse_sql('DROP FUNCTION '+identity+';')
    require(len(signature)==1 and isinstance(signature[0].stmt,ast.DropStmt),'Invalid function signature.')
    signature_types=tuple(RawStream()(value) for value in (signature[0].stmt.objects[0].objargs or ()))
    declared_types=tuple(RawStream()(parameter.argType) for parameter in (statement.parameters or ())
                         if parameter.mode.name not in ('FUNC_PARAM_OUT','FUNC_PARAM_TABLE'))
    require(signature_types==declared_types,'Function argument types differ from evidence identity.')
    options={option.defname:option.arg for option in statement.options}
    require('as' in options and len(options['as'])==1, 'Unsupported function body.')
    body=options['as'][0].sval
    require(hashlib.md5(body.replace('\r','').encode()).hexdigest()==function['body_md5'], 'Function source hash mismatch.')
    require(function['owner']=='postgres' and function['config'] in (['search_path=""'],['search_path=']), 'Unexpected function authority configuration.')
    actual_definer=bool(options.get('security') and options['security'].boolval)
    require(actual_definer is function['security_definer'], 'Function security mode differs from evidence.')
    require(type(function['acl']) is str and function['acl'].startswith('{') and function['acl'].endswith('}'), 'Missing raw ACL evidence.')
    require(not any(item.startswith('=') for item in function['acl'][1:-1].split(',')), 'Unexpected PUBLIC function execution.')
    return body


def validate(document):
    if isinstance(document,list):
        require(len(document)==1 and set(document[0])=={'catalog_schema_preflight_json'},'Unexpected schema wrapper.')
        import json
        document=document[0]['catalog_schema_preflight_json']
        document=json.loads(document) if isinstance(document,str) else document
    require(type(document) is dict and document.get('export_format')=='rosago_catalog_schema_preflight_v1','Invalid schema export format.')
    require(document.get('owner_selected_project_ref')==TARGET and document.get('project_identity_requires_dashboard_confirmation') is True,'Project evidence mismatch.')
    require(document.get('database_role')=='postgres' and document.get('transaction_read_only')=='on','Read-only owner evidence missing.')
    timestamp(document['exported_at'])
    require(type(document.get('migration_history_relation_present')) is bool,'Migration history presence not reported.')
    require({c['name'] for c in document['columns']}==FIELDS and len(document['columns'])==len(FIELDS),'Destination columns differ from reviewed baseline.')
    tables={r['table']:r for r in document['table_security']}
    require(set(tables)=={'places','itinerary_drafts','admin_destination_audit'} and
            all(r['owner']=='postgres' and r['rls_enabled'] is True and r['force_rls'] is False for r in tables.values()),'Table RLS/ownership baseline differs.')
    names={}
    for function in document['functions']:
        function_body(function)
        name=function['identity'].split('(')[0].split('.')[-1]
        require(name not in names,'Unexpected overloaded function inventory.')
        names[name]=function
    for name,digest in TARGETS.items():
        require(name in names and names[name]['body_md5']==digest,'Target function differs from reviewed local baseline.')
    require(names['rosago_admin_mutate_destination_unlogged']['acl']=='{postgres=X/postgres}'
            and names['rosago_admin_mutate_destination']['acl']=='{postgres=X/postgres,authenticated=X/postgres}'
            and names['rosago_itinerary_interests_valid']['acl']=='{postgres=X/postgres}', 'Mutation/validator raw execution permissions differ.')
    for constraint in document['constraints']:
        require(constraint['name'].replace('_','').isalnum(),'Unexpected constraint identifier.')
        commands=parse_sql('ALTER TABLE public.places ADD CONSTRAINT "'+constraint['name']+'" '+constraint['definition']+';')
        require(len(commands)==1 and isinstance(commands[0].stmt,ast.AlterTableStmt) and len(commands[0].stmt.cmds)==1,'Unexpected constraint definition.')
    require(len({c['name'] for c in document['constraints']})==len(document['constraints']),'Duplicate constraint evidence.')
    allowed={('places','SELECT','anon'),('places','SELECT','authenticated'),
             ('itinerary_drafts','SELECT','authenticated'),('admin_destination_audit','SELECT','authenticated')}
    require(all(g['grantee']=='postgres' or (g['table_name'],g['privilege_type'],g['grantee']) in allowed
                for g in document['table_grants']),'Unexpected direct table grant.')
    policies={(p['tablename'],p['policyname']) for p in document['policies']}
    require({('places','places_select_published'),('places','places_select_admin'),
             ('itinerary_drafts','itinerary_drafts_select_own'),('admin_destination_audit','admin_destination_audit_select')} <= policies,'Required baseline policies missing.')
    return document


def bind_extension(document, draft):
    functions={f['identity'].split('(')[0].split('.')[-1]:f for f in document['functions']}
    constraint=next(c for c in document['constraints'] if c['name']=='places_category_check')
    for variable,digest in (
        ('expected_mutation_body_md5',functions['rosago_admin_mutate_destination_unlogged']['body_md5']),
        ('expected_interests_body_md5',functions['rosago_itinerary_interests_valid']['body_md5']),
        ('expected_category_check_md5',hashlib.md5(constraint['definition'].encode()).hexdigest())):
        old=variable+" constant text := 'UNQUALIFIED_CURRENT_PREFLIGHT_REQUIRED'"
        require(draft.count(old)==1,'SQL baseline token mismatch.')
        draft=draft.replace(old,variable+" constant text := '"+digest+"'")
    # All exported functions are pinned, not just the two changed bodies.
    tests=[]
    for function in document['functions']:
        identity=function['identity']
        if not identity.startswith('public.'):identity='public.'+identity
        require("'" not in identity,'Unsafe function identity.')
        digest=hashlib.md5(function['definition'].replace('\r','').encode()).hexdigest()
        acl=function['acl'].replace("'","''")
        tests.append("    IF pg_catalog.to_regprocedure('"+identity+"') IS NULL OR\n"
            "       pg_catalog.md5(pg_catalog.replace(pg_catalog.pg_get_functiondef(pg_catalog.to_regprocedure('"+identity+"')),pg_catalog.chr(13),''))<>'"+digest+"' THEN\n"
            "        RAISE EXCEPTION 'Exported function definition changed; stop and re-review';\n    END IF;\n"
            "    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_proc p WHERE p.oid=pg_catalog.to_regprocedure('"+identity+"')\n"
            "        AND pg_catalog.pg_get_userbyid(p.proowner)='postgres' AND p.proacl::text='"+acl+"') THEN\n"
            "        RAISE EXCEPTION 'Exported function owner or execution privileges changed';\n    END IF;")
    tests.append("    IF (SELECT count(*) FROM pg_catalog.pg_constraint WHERE conrelid='public.places'::pg_catalog.regclass)<>"+str(len(document['constraints']))+" THEN RAISE EXCEPTION 'Destination constraint inventory changed'; END IF;")
    for constraint in document['constraints']:
        name=constraint['name'];digest=hashlib.md5(constraint['definition'].encode()).hexdigest()
        tests.append("    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_constraint c WHERE c.conrelid='public.places'::pg_catalog.regclass\n"
            "        AND c.conname='"+name+"' AND pg_catalog.md5(pg_catalog.pg_get_constraintdef(c.oid))='"+digest+"') THEN\n"
            "        RAISE EXCEPTION 'Destination constraint definition changed';\n    END IF;")
    guard='DO $preflight_snapshot$\nBEGIN\n'+'\n'.join(tests)+'\nEND;\n$preflight_snapshot$;\n'
    draft=draft.replace('BEGIN;\n','BEGIN;\n'+guard,1)
    return '-- REVIEW ONLY / NOT APPROVED. Bound to owner schema export; no hosted execution.\n'+draft


def main():
    path=ROOT/'local_catalog/production-catalog-schema-preflight.json'
    document=validate(read_json(path))
    bound=bind_extension(document,(ROOT/'local_catalog/catalog_extension.review.sql').read_text(encoding='utf-8'))
    output=ROOT/'local_catalog/catalog_extension.production-bound-v2.review.sql'
    with output.open('x',encoding='utf-8') as stream:stream.write(bound)
    provider=any(f['identity'].split('(')[0].split('.')[-1]=='rosago_provider_session_current' for f in document['functions'])
    report=dict(review_only=True,hosted_changes=0,owner_export_validated=True,target_project_ref=TARGET,
        project_identity='owner_dashboard_attestation_not_independent_mcp',schema_export_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        exported_at=document['exported_at'],function_count=len(document['functions']),column_count=len(document['columns']),
        constraint_count=len(document['constraints']),policy_count=len(document['policies']),index_count=len(document['indexes']),
        migration_history='relation_present' if document['migration_history_relation_present'] else 'relation_absent_not_an_empty_history_claim',
        provider_guards_present_in_snapshot=provider,
        missing_published_coordinate_constraint=not any(c['name']=='places_published_coordinates_check' for c in document['constraints']),
        production_bound_extension_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        hosted_application_approved=False,overall_publication_migration_qualified=False,
        blockers=['Current production lacks evaluation provider-session helper/guards; new verification RPC must fail closed and cannot be enabled without separately reviewed provider authority.',
                  'Mapped-only evidence, aliases/archive decisions, descriptions and category definitions remain pending.',
                  'Exact production-derived clone tests and final atomic/maintenance cutover acceptance are required.',
                  'Export is point-in-time; rerun current-state checks before approved application. Existing installed evaluation security SQL is not rerun or copied to production.'])
    write_new(ROOT/'local_catalog/schema-preflight-validation-v2.review.json',report)
    print({k:report[k] for k in ('owner_export_validated','function_count','column_count','constraint_count','policy_count','migration_history','provider_guards_present_in_snapshot')})


if __name__=='__main__':main()
