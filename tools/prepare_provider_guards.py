"""Generate review-only RPC/RLS guards from the exact reconstructed baseline.

Called only with a disposable local connection by qualification tooling. This
module never loads credentials, connects to hosted projects or applies SQL.
"""
import hashlib
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
NAMES=('rosago_itinerary_draft_create','rosago_itinerary_draft_update_preferences',
       'rosago_itinerary_draft_store_preview','rosago_itinerary_draft_return_to_editing',
       'rosago_itinerary_draft_adjust_preview','rosago_admin_mutate_destination','rosago_admin_operational_overview')

def prepare(db):
    tables=tuple(r[0] for r in db.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"))
    # Inventory comes from the reviewed baseline; stop rather than silently
    # skipping a newly added table or function.
    expected={'profiles','places','trips','trip_places','itinerary_drafts','trip_itinerary',
              'trip_stop_plans','admin_memberships','admin_destination_audit'}
    if set(tables)!=expected:
        raise RuntimeError('Baseline table inventory differs; review required.')
    exposed={r[0] for r in db.execute("""SELECT p.proname FROM pg_proc p
        JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public'
        AND p.prosecdef AND has_function_privilege('authenticated',p.oid,'EXECUTE')""")}
    if exposed!=set(NAMES):raise RuntimeError('Exposed definer RPC inventory differs.')
    helper=(ROOT/'evaluation/auth-testing/provider_session_rpc.review.sql').read_text(encoding='utf-8')
    helper=helper[helper.index('CREATE FUNCTION'):helper.rindex('COMMIT;')]
    text=['-- REVIEW ONLY. Evaluation jfaufpfzfhysqkhcdsrs only. Not a hosted migration.\n'
          '-- Adds restrictive RLS and entry guards; preserves existing authorization.\nBEGIN;\n',helper]
    for table in tables:
        text.append(f'CREATE POLICY rosago_current_provider_session ON public.{table}\n'
                    '    AS RESTRICTIVE FOR ALL TO authenticated\n'
                    '    USING ((SELECT public.rosago_provider_session_current()))\n'
                    '    WITH CHECK ((SELECT public.rosago_provider_session_current()));\n')
    functions=list(db.execute("""SELECT p.oid::regprocedure::text,p.prosrc,pg_get_functiondef(p.oid),
        p.prosecdef,l.lanname,p.proconfig,pg_get_userbyid(p.proowner)
        FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_language l ON l.oid=p.prolang
        WHERE n.nspname='public' AND p.proname=ANY(%s) ORDER BY p.proname""",(list(NAMES),)))
    if len(functions)!=7:raise RuntimeError('Baseline RPC inventory differs.')
    for signature,body,definition,definer,language,config,owner in functions:
        if not definer or language!='plpgsql' or config!=['search_path=""'] or owner!='postgres':
            raise RuntimeError('Baseline RPC security attributes differ.')
        guarded,count=re.subn(r'(?im)^BEGIN\b',
            "BEGIN\n    IF NOT public.rosago_provider_session_current() THEN\n"
            "        RAISE EXCEPTION 'Current provider session required' USING ERRCODE='42501';\n"
            "    END IF;",body,count=1)
        if count!=1 or body not in definition:raise RuntimeError('Baseline RPC body differs.')
        digest=hashlib.md5(body.encode()).hexdigest()
        text.append("DO $review_guard$\nBEGIN\n"
            f"    IF NOT EXISTS (SELECT 1 FROM pg_proc p JOIN pg_language l ON l.oid=p.prolang\n"
            f"        WHERE p.oid='{signature}'::regprocedure AND md5(p.prosrc)='{digest}'\n"
            "          AND p.prosecdef AND l.lanname='plpgsql' AND p.proconfig=ARRAY['search_path=\"\"']\n"
            "          AND pg_get_userbyid(p.proowner)='postgres') THEN\n"
            "        RAISE EXCEPTION 'STOP: Reviewed RPC baseline differs';\n"
            "    END IF;\n"
            f"    EXECUTE $review_definition${definition.replace(body,guarded)}$review_definition$;\n"
            "END;\n$review_guard$;\n")
    text.append('COMMIT;\n')
    return '\n'.join(text)
