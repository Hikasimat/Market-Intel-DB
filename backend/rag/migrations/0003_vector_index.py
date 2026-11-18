"""
Vector index for cosine-distance retrieval (PostgreSQL + pgvector only).

HNSW with `vector_cosine_ops` matches the retrieval query, which orders by the
cosine-distance operator `<=>`. HNSW supports up to 2000 dimensions (we use 1024).
Created non-concurrently inside the migration; for very large tables create it
manually with CREATE INDEX CONCURRENTLY and fake this migration.
Reverse only drops the index (never data, never the extension).
"""
from django.db import migrations

INDEX_NAME = "rag_chunk_embedding_hnsw_cos"


def create_index(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        f"CREATE INDEX IF NOT EXISTS {INDEX_NAME} ON rag_knowledgedocumentchunk "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )


def drop_index(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")


class Migration(migrations.Migration):
    dependencies = [("rag", "0002_rag_models")]
    operations = [migrations.RunPython(create_index, drop_index)]
