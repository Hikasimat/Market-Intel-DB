"""Verify pgvector + RAG configuration against the database Django is connected to. Read-only."""
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from rag import conf
from rag.models import KnowledgeDocumentChunk


class Command(BaseCommand):
    help = "Checks PostgreSQL version, pgvector availability/installation, vector column, index, and RAG configuration."

    def add_arguments(self, parser):
        parser.add_argument("--probe-embedding", action="store_true", help="Also call Bedrock once (needs AWS access).")

    def handle(self, *args, **opts):
        problems = []

        def ok(msg):
            self.stdout.write(self.style.SUCCESS(f"[ OK ] {msg}"))

        def bad(msg):
            problems.append(msg)
            self.stdout.write(self.style.ERROR(f"[FAIL] {msg}"))

        def info(msg):
            self.stdout.write(f"[INFO] {msg}")

        if connection.vendor != "postgresql":
            raise CommandError(f"Database vendor is '{connection.vendor}'. RAG requires PostgreSQL + pgvector.")

        with connection.cursor() as cur:
            cur.execute("SHOW server_version")
            version = cur.fetchone()[0]
            cur.execute("SHOW server_version_num")
            vnum = int(cur.fetchone()[0])
            (ok if vnum >= 130000 else bad)(f"PostgreSQL {version} (pgvector needs 13+)")

            cur.execute("SELECT default_version, installed_version FROM pg_available_extensions WHERE name='vector'")
            row = cur.fetchone()
            if row is None:
                bad("pgvector extension is NOT available on this server (Supabase: Dashboard > Database > Extensions; RDS: PG 15.2+).")
            else:
                ok(f"pgvector available (default {row[0]})")
                if row[1]:
                    ok(f"pgvector installed (version {row[1]})")
                else:
                    bad("pgvector is available but not installed. Run `manage.py migrate rag` (migration 0001 enables it).")

            cur.execute("SELECT extname, extversion FROM pg_extension ORDER BY extname")
            info("installed extensions: " + ", ".join(f"{n} {v}" for n, v in cur.fetchall()))

            cur.execute("SELECT rolsuper, rolcreatedb FROM pg_roles WHERE rolname = current_user")
            info("role flags (superuser, createdb): %s" % (cur.fetchone(),))

            table = KnowledgeDocumentChunk._meta.db_table
            cur.execute("SELECT to_regclass(%s)", [table])
            if cur.fetchone()[0] is None:
                bad(f"table {table} missing - run migrations")
            else:
                cur.execute(
                    "SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a "
                    "WHERE a.attrelid = %s::regclass AND a.attname = 'embedding'", [table],
                )
                col = cur.fetchone()
                expected = f"vector({conf.embedding_dimensions()})"
                (ok if col and col[0] == expected else bad)(f"embedding column type {col[0] if col else None} (expected {expected})")
                cur.execute("SELECT indexdef FROM pg_indexes WHERE tablename = %s AND indexdef ILIKE '%%hnsw%%'", [table])
                idx = cur.fetchone()
                (ok if idx else bad)("HNSW cosine index present" if idx else "HNSW index missing (migration 0003)")
                if idx and "vector_cosine_ops" not in idx[0]:
                    bad("HNSW index is not built with vector_cosine_ops (retrieval uses cosine distance)")

        try:
            model = conf.embedding_model_id()
            ok(f"embedding model {model}, dimensions {conf.embedding_dimensions()}, region {conf.aws_region()}")
            from rag.services import embedding_service

            embedding_service.validate_configuration()
            ok("embedding configuration consistent with the vector column")
        except Exception as exc:
            bad(f"embedding configuration: {exc}")

        info(f"storage backend: {conf.storage_backend()}  queue backend: {conf.queue_backend()}")
        if conf.storage_backend() == "s3" and not conf.s3_bucket():
            bad("RAG_STORAGE_BACKEND=s3 but no RAG_S3_BUCKET_NAME / AWS_STORAGE_BUCKET_NAME")
        if conf.queue_backend() == "sqs" and not conf.ingestion_queue_url():
            bad("RAG_QUEUE_BACKEND=sqs but RAG_INGESTION_QUEUE_URL is empty")

        if opts["probe_embedding"]:
            try:
                from rag.services import embedding_service

                vec = embedding_service.embed_query("connectivity probe")
                ok(f"Bedrock embedding call succeeded (dim {len(vec)})")
            except Exception as exc:
                bad(f"Bedrock embedding call failed: {exc}")

        if problems:
            raise CommandError(f"{len(problems)} check(s) failed.")
        self.stdout.write(self.style.SUCCESS("Vector setup verified."))
