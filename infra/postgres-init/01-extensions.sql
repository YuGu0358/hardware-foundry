-- Phase 0: enable required Postgres extensions
-- Runs once on first boot of the foundry-postgres container.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
-- pgvector kept as small-scale fallback; Qdrant is the primary vector store
CREATE EXTENSION IF NOT EXISTS vector;
