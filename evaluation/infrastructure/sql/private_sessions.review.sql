-- REVIEW ONLY. Evaluation jfaufpfzfhysqkhcdsrs; no hosted execution approved.
-- Connect as a trusted owner. A separately approved credential step is needed
-- to enable this NOLOGIN role for a verified-TLS private SQL connection.
BEGIN;
CREATE ROLE rosago_session_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOINHERIT NOREPLICATION NOBYPASSRLS;
CREATE SCHEMA rosago_session AUTHORIZATION postgres;
REVOKE ALL ON SCHEMA rosago_session FROM PUBLIC,anon,authenticated,service_role;
CREATE TABLE rosago_session.payloads (
    key text PRIMARY KEY CHECK (
        key ~ '^[A-Za-z0-9_-]{1,64}:sessions:v3:(user|admin):[A-Za-z0-9_-]{1,64}:[a-z_]{1,20}:[a-f0-9]{64}$'
    ),
    ciphertext bytea NOT NULL CHECK (octet_length(ciphertext) BETWEEN 1 AND 45000),
    expires double precision NOT NULL CHECK (expires > 0 AND expires < 'Infinity'::float8)
);
CREATE INDEX payloads_expiry ON rosago_session.payloads(expires);
ALTER TABLE rosago_session.payloads ENABLE ROW LEVEL SECURITY;
ALTER TABLE rosago_session.payloads FORCE ROW LEVEL SECURITY;
REVOKE ALL ON rosago_session.payloads FROM PUBLIC,anon,authenticated,service_role;
GRANT USAGE ON SCHEMA rosago_session TO rosago_session_app;
GRANT SELECT,INSERT,UPDATE,DELETE ON rosago_session.payloads TO rosago_session_app;
CREATE POLICY session_payload_role ON rosago_session.payloads
    TO rosago_session_app USING (true) WITH CHECK (true);
ALTER DEFAULT PRIVILEGES IN SCHEMA rosago_session REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA rosago_session REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
COMMIT;
