-- NEW REVIEW ONLY. Evaluation jfaufpfzfhysqkhcdsrs. NOT APPROVED OR APPLIED.
-- Candidate for a server-only SQL data path with the hosted Data API DISABLED.
-- This does not disable any API, alter existing RLS, or qualify Auth recovery.
BEGIN;
CREATE ROLE rosago_data_gateway NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOINHERIT NOREPLICATION NOBYPASSRLS;
-- The trusted server selects one existing low-privilege RLS role per transaction.
-- No membership is granted to either API role or any Auth/application account.
GRANT anon, authenticated TO rosago_data_gateway WITH INHERIT FALSE, SET TRUE;
COMMIT;
