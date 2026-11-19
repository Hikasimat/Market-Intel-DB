import os
import dj_database_url
from django.core.management.base import BaseCommand
from django.db import connections, transaction


class Command(BaseCommand):
    help = (
        "Safely delete ONLY WhatsApp chat and conversation data while preserving all users, "
        "connected WhatsApp sessions, configurations, AI settings, opt-outs, CRM prospects, "
        "meetings, tasks, and email records."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show counts of records that would be deleted without modifying the database.",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Confirm permanent deletion of WhatsApp chat and conversation records.",
        )
        parser.add_argument(
            "--target",
            choices=["default", "local", "production", "both"],
            default="default",
            help="Target database: default (Django DATABASES['default']), local (DB_* env), production (DATABASE_URL), or both.",
        )

    def _register_alias_if_needed(self, target_name: str) -> str:
        if target_name == "default":
            return "default"

        if target_name == "local":
            cfg = {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": os.environ.get("DB_NAME", "marketintel"),
                "USER": os.environ.get("DB_USER", "postgres"),
                "PASSWORD": os.environ.get("DB_PASSWORD", ""),
                "HOST": os.environ.get("DB_HOST", "localhost"),
                "PORT": os.environ.get("DB_PORT", "5432"),
                "ATOMIC_REQUESTS": False,
                "AUTOCOMMIT": True,
                "CONN_MAX_AGE": 0,
                "CONN_HEALTH_CHECKS": True,
                "OPTIONS": {},
                "TIME_ZONE": None,
            }
            connections.databases["purge_local"] = cfg
            return "purge_local"

        if target_name == "production":
            db_url = os.environ.get("DATABASE_URL", "").strip()
            if not db_url:
                raise RuntimeError("DATABASE_URL is not configured in environment.")
            cfg = dj_database_url.parse(
                db_url,
                conn_max_age=0,
                conn_health_checks=True,
                ssl_require=os.getenv("DB_SSL_REQUIRE", "true").lower() == "true",
            )
            cfg.setdefault("ATOMIC_REQUESTS", False)
            cfg.setdefault("AUTOCOMMIT", True)
            cfg.setdefault("OPTIONS", {})
            cfg.setdefault("TIME_ZONE", None)
            connections.databases["purge_production"] = cfg
            return "purge_production"

        raise ValueError(f"Unsupported target: {target_name}")

    def _purge_single_db(self, alias: str, label: str, *, dry_run: bool, confirmed: bool) -> dict:
        from django.contrib.auth import get_user_model
        from prospects.models import Meeting, PreTask, Prospect
        from whatsapp.models import (
            WhatsAppAuditLog,
            WhatsAppConfiguration,
            WhatsAppConversation,
            WhatsAppEvent,
            WhatsAppMessage,
            WhatsAppOptOut,
            WhatsAppSession,
        )
        from whatsapp_ai.models import (
            WhatsAppAIAutoReplyConfig,
            WhatsAppAIReplyLog,
            WhatsAppAssistantState,
            WhatsAppMeetingRequest,
        )

        User = get_user_model()
        existing_tables = set(connections[alias].introspection.table_names())

        def _safe_count(model_cls):
            if model_cls._meta.db_table not in existing_tables:
                return 0
            return model_cls.objects.using(alias).count()

        counts_before = {
            "conversations": _safe_count(WhatsAppConversation),
            "messages": _safe_count(WhatsAppMessage),
            "ai_reply_logs": _safe_count(WhatsAppAIReplyLog),
            "assistant_states": _safe_count(WhatsAppAssistantState),
            "meeting_requests": _safe_count(WhatsAppMeetingRequest),
            "preserved_sessions": _safe_count(WhatsAppSession),
            "preserved_ai_configs": _safe_count(WhatsAppAIAutoReplyConfig),
            "preserved_configs": _safe_count(WhatsAppConfiguration),
            "preserved_opt_outs": _safe_count(WhatsAppOptOut),
            "preserved_users": _safe_count(User),
            "preserved_prospects": _safe_count(Prospect),
            "preserved_meetings": _safe_count(Meeting),
            "preserved_pre_tasks": _safe_count(PreTask),
            "preserved_audit_logs": _safe_count(WhatsAppAuditLog),
        }

        if WhatsAppConversation._meta.db_table not in existing_tables:
            self.stdout.write(self.style.WARNING(f"[{label}] No WhatsApp conversation table found (tables={len(existing_tables)}); nothing to purge."))
            return {"status": "no_whatsapp_tables", "before": counts_before, "after": counts_before}

        self.stdout.write(f"[{label}] Pre-purge summary: {counts_before}")
        if dry_run or not confirmed:
            if not dry_run and not confirmed:
                self.stdout.write(self.style.WARNING(f"[{label}] Skipped execution (pass --yes to apply deletion)."))
            return {"status": "dry_run", "before": counts_before, "after": counts_before}

        with transaction.atomic(using=alias):
            if PreTask._meta.db_table in existing_tables:
                PreTask.objects.using(alias).filter(whatsapp_conversation__isnull=False).update(
                    whatsapp_conversation=None
                )
            if WhatsAppEvent._meta.db_table in existing_tables:
                WhatsAppEvent.objects.using(alias).filter(whatsapp_message__isnull=False).update(
                    whatsapp_message=None
                )
            deleted_logs = (
                WhatsAppAIReplyLog.objects.using(alias).all().delete()[0]
                if WhatsAppAIReplyLog._meta.db_table in existing_tables
                else 0
            )
            deleted_states = (
                WhatsAppAssistantState.objects.using(alias).all().delete()[0]
                if WhatsAppAssistantState._meta.db_table in existing_tables
                else 0
            )
            deleted_mreqs = (
                WhatsAppMeetingRequest.objects.using(alias).all().delete()[0]
                if WhatsAppMeetingRequest._meta.db_table in existing_tables
                else 0
            )
            deleted_msgs = (
                WhatsAppMessage.objects.using(alias).all().delete()[0]
                if WhatsAppMessage._meta.db_table in existing_tables
                else 0
            )
            deleted_convs = WhatsAppConversation.objects.using(alias).all().delete()[0]

            if WhatsAppSession._meta.db_table in existing_tables:
                WhatsAppSession.objects.using(alias).filter(last_synced_at__isnull=False).update(
                    last_synced_at=None
                )

        counts_after = {
            "conversations": _safe_count(WhatsAppConversation),
            "messages": _safe_count(WhatsAppMessage),
            "ai_reply_logs": _safe_count(WhatsAppAIReplyLog),
            "assistant_states": _safe_count(WhatsAppAssistantState),
            "meeting_requests": _safe_count(WhatsAppMeetingRequest),
            "preserved_sessions": _safe_count(WhatsAppSession),
            "preserved_ai_configs": _safe_count(WhatsAppAIAutoReplyConfig),
            "preserved_configs": _safe_count(WhatsAppConfiguration),
            "preserved_opt_outs": _safe_count(WhatsAppOptOut),
            "preserved_users": _safe_count(User),
            "preserved_prospects": _safe_count(Prospect),
            "preserved_meetings": _safe_count(Meeting),
            "preserved_pre_tasks": _safe_count(PreTask),
            "preserved_audit_logs": _safe_count(WhatsAppAuditLog),
        }
        self.stdout.write(
            self.style.SUCCESS(
                f"[{label}] Deleted logs={deleted_logs}, states={deleted_states}, "
                f"meeting_requests={deleted_mreqs}, messages={deleted_msgs}, conversations={deleted_convs}. "
                f"Preserved sessions={counts_after['preserved_sessions']}, users={counts_after['preserved_users']}, "
                f"meetings={counts_after['preserved_meetings']}, tasks={counts_after['preserved_pre_tasks']}."
            )
        )
        return {"status": "purged", "before": counts_before, "after": counts_after}

    def handle(self, *args, **options):
        dry_run = bool(options["dry_run"])
        confirmed = bool(options["yes"])
        target = options["target"]

        targets = ["local", "production"] if target == "both" else [target]
        for tgt in targets:
            alias = self._register_alias_if_needed(tgt)
            try:
                self._purge_single_db(alias, tgt, dry_run=dry_run, confirmed=confirmed)
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"[{tgt}] Purge failed: {exc}"))
                raise
