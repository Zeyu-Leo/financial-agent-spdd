-- 0001_create_tables.sql — canonical DDL for the RAG v0 corpus.
--
-- This file is the single source of truth for the three Task 2 tables
-- (complaints, docs, doc_embeddings). It is applied by
-- app.core.db.apply_schema, which substitutes the /* EMBEDDING_DIM */
-- placeholder with Settings.embedding_dim before execution so the same
-- SQL works for a 768-d or a 1536-d embedding model.
--
-- Idempotent: every statement uses IF NOT EXISTS so re-running is safe.
-- The pgvector extension itself is created by ensure_pgvector_extension.

-- Structured CFPB complaint rows (mirrors complaints_sample.csv).
CREATE TABLE IF NOT EXISTS complaints (
    id                bigserial PRIMARY KEY,
    complaint_id      text UNIQUE NOT NULL,
    date_received     date NOT NULL,
    product           text NOT NULL,
    sub_product       text,
    issue             text,
    sub_issue         text,
    company           text,
    state             text,
    narrative         text,
    company_response  text,
    consumer_disputed text
);

-- One row per document chunk (metadata + raw text).
CREATE TABLE IF NOT EXISTS docs (
    id           bigserial PRIMARY KEY,
    source_file  text NOT NULL,
    title        text,
    section      text,
    chunk_index  int  NOT NULL,
    raw_text     text NOT NULL,
    UNIQUE (source_file, chunk_index)
);

-- One embedding vector per chunk. Dimension is parameterised; it must
-- match Settings.embedding_dim (768 for nomic-embed-text).
CREATE TABLE IF NOT EXISTS doc_embeddings (
    doc_id     bigint PRIMARY KEY REFERENCES docs(id) ON DELETE CASCADE,
    embedding  vector(/* EMBEDDING_DIM */) NOT NULL
);
