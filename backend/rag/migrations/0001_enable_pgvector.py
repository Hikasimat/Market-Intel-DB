"""
Enable the pgvector extension - safely.

Checks (PostgreSQL only; no-op on other vendors such as the SQLite unit-test DB):
  1. server version is supported by pgvector (PostgreSQL >= 13),
  2. the `vector` extension is AVAILABLE on this server (pg_available_extensions),
  3. whether it is already installed (then nothing is changed),
  4. the connected role may create it.
If the extension cannot be enabled the migration stops with the exact problem
instead of silently substituting another vector store.

The reverse migration is intentionally a no-op: dropping the extension would be
destructive (it would drop every vector column in the database).
"""
from django.db import migrations


def enable_pgvector(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cur:
        cur.execute("SHOW server_version_num")
        version_num = int(cur.fetchone()[0])
        if version_num < 130000:
            raise RuntimeError(
                f"pgvector requires PostgreSQL 13+, but this server reports version_num={version_num}."
            )
        cur.execute("SELECT installed_version, default_version FROM pg_available_extensions WHERE name = 'vector'")
        row = cur.fetchone()
        if row is None:
            raise RuntimeError(
                "The 'vector' (pgvector) extension is NOT available on this PostgreSQL server. "
                "Local/Supabase: enable it in Dashboard > Database > Extensions. "
                "AWS RDS: use PostgreSQL 15.2+/16/17 (pgvector is bundled) and run "
                "'CREATE EXTENSION vector;' as a role with rds_superuser. No fallback vector store is used."
            )
        if row[0]:
            return  # already installed - do not touch it
        try:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        except Exception as exc:  # insufficient privilege etc. - report precisely
            raise RuntimeError(
                f"The 'vector' extension is available but could not be created by the current "
                f"database role (permissions?): {exc}. Ask a privileged role to run "
                "'CREATE EXTENSION vector;' and re-run migrate."
            ) from exc


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [migrations.RunPython(enable_pgvector, migrations.RunPython.noop)]
