-- Separate owner approval required. Containment, not Auth/database restoration.
BEGIN;
DO $owner98_rollback_gate$ BEGIN RAISE EXCEPTION 'UNAPPROVED_OWNER98_CONTAINMENT'; END $owner98_rollback_gate$;
CREATE FUNCTION rosago_owner_catalog98.contain()
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=''
AS $contain$
DECLARE saved rosago_owner_catalog98.batches%ROWTYPE; old jsonb; after_row jsonb; ordinal integer;
BEGIN
 IF SESSION_USER<>'postgres' OR CURRENT_USER<>'postgres' THEN
  RAISE EXCEPTION 'Trusted owner connection required' USING ERRCODE='42501'; END IF;
 IF current_setting('transaction_isolation')<>'serializable' THEN RAISE EXCEPTION 'Serializable owner transaction required'; END IF;
 SELECT * INTO STRICT saved FROM rosago_owner_catalog98.batches FOR UPDATE;
 IF saved.status<>'applied' THEN RAISE EXCEPTION 'No uncontained applied batch'; END IF;
 LOCK TABLE public.places IN SHARE ROW EXCLUSIVE MODE;
 FOR old IN SELECT value FROM jsonb_array_elements(saved.after_rows) LOOP
  IF NOT EXISTS(SELECT 1 FROM public.places p WHERE p.id=(old->>'id')::uuid
      AND to_jsonb(p)=to_jsonb(jsonb_populate_record(NULL::public.places,old))) THEN
   RAISE EXCEPTION 'Post-publication drift: inspect before containment'; END IF;
 END LOOP;
 SELECT coalesce(max(e.ordinal),0) INTO ordinal FROM rosago_owner_catalog98.events e WHERE e.batch_id=saved.batch_id;
 FOR old IN SELECT value FROM jsonb_array_elements(saved.after_rows) WHERE value->>'status'='published' LOOP
  UPDATE public.places SET status='draft' WHERE id=(old->>'id')::uuid RETURNING to_jsonb(places.*) INTO after_row;
  ordinal:=ordinal+1;
  INSERT INTO rosago_owner_catalog98.events(batch_id,ordinal,destination_id,action,operator_name,before_row,after_row)
   VALUES(saved.batch_id,ordinal,(old->>'id')::uuid,'owner_contain',SESSION_USER,old,after_row);
 END LOOP;
 UPDATE rosago_owner_catalog98.batches SET status='contained',contained_at=clock_timestamp() WHERE batch_id=saved.batch_id;
 IF (SELECT count(*) FROM public.places)<>120 OR EXISTS(SELECT 1 FROM public.places WHERE status='published')
    OR (SELECT count(*) FROM public.places WHERE status='draft')<>107
    OR (SELECT count(*) FROM public.places WHERE status='archived')<>13 THEN
  RAISE EXCEPTION 'Containment count mismatch'; END IF;
 RETURN jsonb_build_object('published',0,'draft',107,'archived',13,'total',120,'deleted',0,'images_deleted',0);
END $contain$;
ALTER FUNCTION rosago_owner_catalog98.contain() OWNER TO postgres;
REVOKE ALL ON FUNCTION rosago_owner_catalog98.contain() FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION rosago_owner_catalog98.contain() TO postgres;
COMMIT;
