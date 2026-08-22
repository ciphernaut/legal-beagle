-- Runs once, on an empty data directory, as part of the pgvector/pgvector:pg16 entrypoint.
-- POSTGRES_DB creates `legal`; the test database and the vector extension are ours to make.
-- The extension is per-database, so it must be created inside each one.

CREATE DATABASE legal_test;

\connect legal
CREATE EXTENSION IF NOT EXISTS vector;

\connect legal_test
CREATE EXTENSION IF NOT EXISTS vector;
