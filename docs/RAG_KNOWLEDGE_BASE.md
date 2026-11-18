# Market Intel DB — WhatsApp AI RAG Knowledge Base (`rag`)

## 1. Architecture Overview

The `rag` Django application implements a tenant-isolated **Retrieval-Augmented Generation (RAG)** pipeline for Market Intel DB's WhatsApp AI automation:

- **Vector Database**: PostgreSQL + `pgvector` (`vector(1024)` column + HNSW cosine index `vector_cosine_ops`) using the existing Django database connection:
  - **Local Development**: Existing Supabase PostgreSQL database (`pgvector` 0.8.2).
  - **Production**: Existing Amazon RDS PostgreSQL database (`pgvector`).
- **Document Storage**:
  - **Local Development**: Dedicated private directory under `MEDIA_ROOT/rag_private` (explicitly blocked from public `/media/` serving).
  - **Production**: Private Amazon S3 bucket (`AES256` server-side encryption, tenant-prefixed object keys, EC2 IAM role via `boto3`'s default credential chain).
- **Embeddings**: Amazon Bedrock Titan Text Embeddings V2 (`amazon.titan-embed-text-v2:0`, 1024 dimensions) for both document chunks and customer questions.
- **Grounded Generation**: Existing Google Gemini configuration with separated `systemInstruction`, strict JSON schema validation, citation verification, literal number/contact grounding checks, and optional LLM fact-checking.
- **Strict RAG Mode**: Opt-in per `WhatsAppSession` (`SessionRAGConfig.strict_rag_enabled`). When enabled, the WhatsApp AI answers **exclusively** from the session's assigned active `KnowledgeBase` and refuses all unrelated or unsupported questions without ever falling back to general Gemini knowledge.

---

## 2. Django Application Structure (`backend/rag/`)

```text
backend/rag/
├── __init__.py
├── admin.py
├── apps.py
├── conf.py
├── constants.py
├── exceptions.py
├── fields.py
├── integration.py
├── models.py
├── permissions.py
├── serializers.py
├── tasks.py
├── urls.py
├── views.py
├── evaluation/
│   ├── __init__.py
│   ├── metrics.py
│   ├── runner.py
│   └── datasets/
│       └── sample_dataset.json
├── management/
│   └── commands/
│       ├── evaluate_rag.py
│       ├── purge_rag_query_logs.py
│       ├── reembed_rag.py
│       ├── run_rag_worker.py
│       └── verify_vector_setup.py
├── migrations/
│   ├── 0001_enable_pgvector.py
│   ├── 0002_rag_models.py
│   └── 0003_vector_index.py
├── services/
│   ├── __init__.py
│   ├── answer_generation_service.py
│   ├── answer_validation_service.py
│   ├── chunking_service.py
│   ├── context_builder_service.py
│   ├── document_parser_service.py
│   ├── document_upload_service.py
│   ├── document_validation_service.py
│   ├── embedding_service.py
│   ├── guardrails_service.py
│   ├── knowledge_base_service.py
│   ├── query_understanding_service.py
│   ├── rag_pipeline_service.py
│   ├── reranking_service.py
│   ├── retrieval_service.py
│   ├── storage_service.py
│   ├── text_extraction_service.py
│   └── vector_store_service.py
├── tests/
│   ├── __init__.py
│   ├── helpers.py
│   ├── test_answer_accuracy.py
│   ├── test_chunking.py
│   ├── test_document_parsing.py
│   ├── test_document_upload.py
│   ├── test_embeddings.py
│   ├── test_rag_guardrails.py
│   ├── test_tenant_isolation.py
│   ├── test_vector_retrieval.py
│   └── test_whatsapp_integration.py
└── workers/
    ├── __init__.py
    ├── embedding_worker.py
    └── ingestion_worker.py
```

---

## 3. Database Models & Migrations

### Models (`backend/rag/models.py`)

1. **`KnowledgeBase`**:
   - `id` (UUID PK), `owner` (FK `User`), `company` (nullable FK `companies.Company`), `name`, `description`, `is_active`, `created_at`, `updated_at`.
   - Supports personal knowledge bases (`company=NULL`, isolated to `owner`) and company-level knowledge bases (`company` set, shared only within that company).
2. **`KnowledgeDocument`**:
   - `id` (UUID PK), `knowledge_base` (FK), `original_filename`, `file_type`, `file_size`, `storage_key` (never exposed via API), `mime_type`, `checksum_sha256`, `status` (`UPLOADED`, `VALIDATING`, `PROCESSING`, `CHUNKING`, `EMBEDDING`, `READY`, `FAILED`, `DELETING`), `processing_error`, `total_pages`, `total_chunks`, `version`, `is_active`, `replaces` (self-FK), `processing_attempts`, `processing_started_at`, `ready_at`, `created_by`, `created_at`, `updated_at`.
3. **`KnowledgeDocumentChunk`**:
   - `id` (UUID PK), `document` (FK), `knowledge_base` (denormalized FK for SQL-level tenant filtering), `chunk_index`, `text`, `embedding` (`EmbeddingField(dimensions=1024)` -> `vector(1024)` on PostgreSQL), `embedding_model`, `embedding_dimension`, `page_number`, `sheet_name`, `section_heading`, `metadata` (JSON), `token_count`, `content_checksum`, `created_at`.
4. **`KnowledgeBaseSessionAssignment`**:
   - `id` (UUID PK), `session` (FK `whatsapp.WhatsAppSession`), `knowledge_base` (FK), `is_active`, `created_at`, `updated_at`.
   - Enforces a partial unique constraint (`rag_one_active_assignment_per_session`) so a WhatsApp session has at most one active knowledge base assignment at a time.
5. **`SessionRAGConfig`**:
   - `id` (UUID PK), `session` (OneToOne `whatsapp.WhatsAppSession`), `strict_rag_enabled` (default `False`), `refusal_message`, `top_k`, `min_relevance_threshold`, `updated_by`, `created_at`, `updated_at`.
6. **`RAGQueryLog`**:
   - `id` (UUID PK), `session` (nullable FK), `knowledge_base` (nullable FK), `source` (`whatsapp` | `test`), `question` (truncated), `retrieval_status`, `retrieved_chunk_ids`, `similarity_scores`, `source_document_ids`, `model_used`, `answer_status` (`ANSWERED` | `REFUSED` | `ERROR`), `refusal_reason`, `processing_ms`, `created_at`.
7. **`IngestionJob`**:
   - Local database-backed ingestion queue row (`QUEUED`, `RUNNING`, `DONE`, `FAILED`) used when `RAG_QUEUE_BACKEND=local`.

### Migrations (`backend/rag/migrations/`)

- `0001_enable_pgvector.py`: Verifies PostgreSQL >= 13 and `pg_available_extensions` for `vector`, and runs `CREATE EXTENSION IF NOT EXISTS vector`. Reversible as a safe no-op.
- `0002_rag_models.py`: Creates all relational tables, indexes, and uniqueness constraints.
- `0003_vector_index.py`: Creates the HNSW cosine index `rag_chunk_embedding_hnsw_cos` (`USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)`).

---

## 4. Pipelines & Workflows

### Document Ingestion (`document_upload_service.py` & `ingestion_worker.py`)
1. User authenticates and uploads a file (`PDF`, `DOCX`, `XLSX`, `CSV`, `TXT`, `Markdown`).
2. `document_validation_service.validate_upload` verifies the sanitized filename, extension, MIME type, magic bytes / ZIP structure (including zip-bomb protection), non-empty content, and size limit (`RAG_MAX_DOCUMENT_SIZE_MB`).
3. SHA-256 checksum is calculated. Duplicate checksums in the same KB are rejected; re-uploading an updated file with the same filename increments `version` (`v2`, `v3`, ...).
4. Original bytes are stored in private storage (`storage_service.py`) under a tenant-scoped key (`rag-documents/<tenant>/<kb_id>/<doc_id>/<uuid>.<ext>`).
5. `KnowledgeDocument` is created with `status=UPLOADED`, `is_active=False`, and an ingestion job is queued on transaction commit.
6. `ingestion_worker.process_document` claims the document (`VALIDATING` -> `PROCESSING` -> `CHUNKING` -> `EMBEDDING`), parses blocks (`document_parser_service.py`), chunks while preserving page/sheet/section/table headers (`chunking_service.py`), embeds via Amazon Bedrock (`embedding_service.py`), atomically replaces chunks (`vector_store_service.replace_document_chunks`), verifies stored chunk counts, retires any older version, and marks `status=READY, is_active=True`.

### Vector Retrieval & Tenant Isolation (`vector_store_service.py` & `retrieval_service.py`)
- Every vector query starts from `vector_store_service.base_queryset(kb)`, which filters **in SQL** by:
  - Tenant (`knowledge_base__company_id` or `knowledge_base__owner_id`),
  - `knowledge_base_id=kb.id` and `knowledge_base__is_active=True`,
  - `document__status='READY'` and `document__is_active=True`,
  - `embedding_model` and `embedding_dimension` matching the active configuration.
- Orders by `CosineDistance("embedding", query_embedding)` (`<=>`) with `SET LOCAL hnsw.iterative_scan = relaxed_order`.
- Applies relevance threshold gating (`RAG_MIN_RELEVANCE_THRESHOLD`), deduplication, and lexical overlap reranking.

### Strict RAG Guardrails & Grounded Generation (`rag_pipeline_service.py`)
1. Pre-screens customer questions for prompt-injection patterns (`guardrails_service.py`).
2. Resolves `WhatsAppSession -> active KnowledgeBaseSessionAssignment -> active KnowledgeBase -> READY documents` and verifies tenant compatibility (`knowledge_base_service.resolve_kb_for_session`).
3. Sanitizes all retrieved evidence and wraps chunks in `<evidence id="..." source="...">` delimiters while placing rules in Gemini's top-level `systemInstruction`.
4. Requires structured JSON matching `ANSWER_SCHEMA` (`answer`, `can_answer`, `source_chunk_ids`, `confidence`, `refusal_reason`).
5. `answer_validation_service.validate` independently verifies:
   - Schema validity and model confidence,
   - Every `source_chunk_id` belongs to the retrieved prompt context,
   - Zero internal prompt/marker leakage,
   - Every number, email, and URL in the answer literally appears in the cited evidence chunks,
   - Lexical grounding ratio and optional second-pass LLM fact-check (`RAG_LLM_GROUNDING_CHECK`).
6. On validation failure, retries once with `STRICT_RETRY_ADDENDUM`; if still invalid, returns the fixed refusal message.

### WhatsApp Integration (`rag/integration.py` & `whatsapp_ai/gemini_service.py`)
- Hooked into `whatsapp_ai.gemini_service.process_ai_auto_reply` via `_try_strict_rag_reply`:
  - If `SessionRAGConfig.strict_rag_enabled` is `False` (default for all existing sessions), returns `None` and the existing unrestricted Gemini workflow runs unchanged.
  - If `strict_rag_enabled` is `True`, `maybe_generate_strict_reply` runs the Strict RAG pipeline and returns either the grounded answer, the configured refusal message, or a skip code on infrastructure outage—never falling back to general Gemini knowledge.
  - Outbound WAHA `send_text`, conversation history sync, `WhatsAppMessage` persistence, opt-out handling, and `WhatsAppAIReplyLog` idempotency remain 100% handled by the existing `whatsapp_ai` code.

---

## 5. API Documentation (`/api/rag/`)

All endpoints require authentication (`CookieJWTAuthentication` + `CanUseRAG`).

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET`, `POST` | `/api/rag/knowledge-bases/` | List accessible KBs or create a new KB (`name`, `description`, `company_level`). |
| `GET`, `PATCH`, `DELETE` | `/api/rag/knowledge-bases/{id}/` | Retrieve, update (`name`, `description`, `is_active`), or safely delete a KB. |
| `GET`, `POST` | `/api/rag/knowledge-bases/{id}/documents/` | List documents in KB or upload a new document (`multipart/form-data`, field `file`). |
| `GET` | `/api/rag/knowledge-bases/{id}/statistics/` | Document counts by status, total bytes, total chunks, readiness, assigned sessions. |
| `GET`, `DELETE` | `/api/rag/documents/{id}/` | Retrieve document metadata or safely delete document + vector chunks + storage object. |
| `POST` | `/api/rag/documents/{id}/retry/` | Re-queue a `FAILED` or `UPLOADED` document for ingestion. |
| `GET`, `POST` | `/api/rag/session-assignments/` | List or create/activate a `WhatsAppSession` ↔ `KnowledgeBase` assignment. |
| `PATCH`, `DELETE` | `/api/rag/session-assignments/{id}/` | Activate/deactivate or remove a session assignment. |
| `GET` | `/api/rag/session-settings/` | List AI & Strict RAG settings across the user's WhatsApp sessions. |
| `GET`, `PATCH` | `/api/rag/session-settings/{session_id}/` | Update `ai_enabled`, `strict_rag_enabled`, and (for Managers/SuperAdmins) `top_k`, `min_relevance_threshold`, `refusal_message`. |
| `POST` | `/api/rag/test-query/` | Safe sandbox query (`question` + `knowledge_base_id` or `session_id`); never sends WhatsApp messages. |
| `GET` | `/api/rag/health/` | Reports database vendor, `pgvector` installation status, embedding model/dimensions, storage and queue backends. |

---

## 6. Setup & Deployment Instructions

### Local Supabase PostgreSQL Setup
1. Keep your existing `DATABASE_URL` / `DB_*` settings in `backend/.env`.
2. Ensure `vector` extension is enabled (migration `0001_enable_pgvector` enables it automatically; or in Supabase Dashboard → Database → Extensions → enable `vector`).
3. Run migrations and verify:
   ```bash
   python manage.py migrate rag
   python manage.py verify_vector_setup
   ```
4. Start the local ingestion worker in a separate terminal:
   ```bash
   python manage.py run_rag_worker --poll-interval 3
   ```

### Production AWS RDS PostgreSQL + pgvector Setup
1. Ensure your RDS PostgreSQL instance runs PostgreSQL 15.2+, 16, or 17 (`pgvector` is bundled by AWS RDS).
2. Connect once as the master user (member of `rds_superuser`) and run:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```
3. Run `python manage.py migrate` and `python manage.py verify_vector_setup --probe-embedding`.

### Amazon S3, Bedrock IAM, and SQS Configuration
Attach the following least-privilege IAM permissions to the **EC2 Instance Role** (no hardcoded AWS keys):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BedrockEmbeddings",
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel"],
      "Resource": "arn:aws:bedrock:ap-south-1::foundation-model/amazon.titan-embed-text-v2:0"
    },
    {
      "Sid": "PrivateRAGDocumentsS3",
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::YOUR_BUCKET_NAME/rag-documents/*"
    },
    {
      "Sid": "RAGIngestionSQS",
      "Effect": "Allow",
      "Action": ["sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"],
      "Resource": [
        "arn:aws:sqs:ap-south-1:YOUR_ACCOUNT_ID:marketintel-rag-ingestion",
        "arn:aws:sqs:ap-south-1:YOUR_ACCOUNT_ID:marketintel-rag-ingestion-dlq"
      ]
    }
  ]
}
```

- **S3 Bucket Settings**: Block all public access (`BlockPublicAcls=true`, `IgnorePublicAcls=true`, `BlockPublicPolicy=true`, `RestrictPublicBuckets=true`), enable default SSE-S3 (`AES256`).
- **SQS Queue Settings** (when `RAG_QUEUE_BACKEND=sqs`): Standard queue `marketintel-rag-ingestion` with `VisibilityTimeout = 900` seconds and a redrive policy (`maxReceiveCount = 3`) pointing to `marketintel-rag-ingestion-dlq`.

---

## 7. Known Limitations

1. **Scanned PDFs**: Text-based PDFs are parsed locally via `pypdf`. Scanned/image-only PDFs are rejected with `PDF_NEEDS_OCR` unless `RAG_OCR_BACKEND=textract` and `RAG_STORAGE_BACKEND=s3` are enabled in production.
2. **Encrypted/Password-Protected Office/PDF Files**: Rejected during parsing with a clear error message.
3. **Embedding Dimension Changes**: The `vector(1024)` column is sized for `amazon.titan-embed-text-v2:0` (1024 dims). Changing models with the same dimension uses `python manage.py reembed_rag`; changing dimensions requires a schema migration plus `reembed_rag`.
