"""
Smoke test suite for MarketIntel DB backend.
Validates Django startup, database connectivity, system checks, URL configuration,
and core API security boundaries in CI/CD and deployment pipelines.
Exits with code 0 on success, or code 1 on failure.
"""

import os
import sys
import django

# Ensure settings module is configured
if not os.environ.get("DJANGO_SETTINGS_MODULE"):
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"

backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Ensure essential settings are present in CI or standalone test environments
if not os.environ.get("SECRET_KEY"):
    os.environ["SECRET_KEY"] = "ci-synthetic-smoke-test-secret-key-32-chars-minimum!"

if not os.environ.get("DEBUG"):
    os.environ["DEBUG"] = "True"

if not os.environ.get("MAIL_CREDENTIALS_ENCRYPTION_KEY"):
    from cryptography.fernet import Fernet
    os.environ["MAIL_CREDENTIALS_ENCRYPTION_KEY"] = Fernet.generate_key().decode("utf-8")

if not os.environ.get("WHATSAPP_WEBHOOK_SECRET"):
    os.environ["WHATSAPP_WEBHOOK_SECRET"] = "ci_smoke_test_webhook_secret_key_32_bytes_min!"

django.setup()

from django.core.management import call_command
from django.test import Client
from django.urls import resolve
from django.contrib.auth.models import User
from accounts.models import UserProfile
from prospects.models import Prospect, LeadQualification
from market_events.models import MarketEvent
from whatsapp.models import WhatsAppSession, WhatsAppMessage
from digital_marketing.models import SocialPost

results = []

def record(name, status, details=""):
    results.append({"name": name, "status": status, "details": details})
    marker = "PASS" if status == "PASS" else "FAIL"
    print(f"[{marker}] {name} - {details}")

def main():
    print("=" * 60)
    print("MarketIntel DB — Backend Smoke Test Suite")
    print("=" * 60)

    # 1. System checks
    try:
        call_command("check", verbosity=0)
        record("Django System Check (manage.py check)", "PASS", "0 issues identified")
    except Exception as e:
        record("Django System Check (manage.py check)", "FAIL", str(e))

    # 2. URL resolution
    try:
        match_login = resolve("/api/auth/login/")
        match_prospects = resolve("/api/prospects/")
        record("URL Routing Configuration", "PASS", f"Resolved auth ({match_login.func.__name__}) and prospects")
    except Exception as e:
        record("URL Routing Configuration", "FAIL", str(e))

    client = Client(SERVER_NAME="127.0.0.1")

    # 3. OpenAPI Schema and Health endpoints
    try:
        res = client.get("/api/schema/")
        if res.status_code == 200:
            record("OpenAPI Schema Endpoint (/api/schema/)", "PASS", f"HTTP {res.status_code}")
        else:
            record("OpenAPI Schema Endpoint (/api/schema/)", "FAIL", f"Expected 200, got {res.status_code}")
    except Exception as e:
        record("OpenAPI Schema Endpoint (/api/schema/)", "FAIL", str(e))

    try:
        res_health = client.get("/api/whatsapp/health/")
        if res_health.status_code == 200:
            record("WhatsApp Health Endpoint (/api/whatsapp/health/)", "PASS", f"HTTP {res_health.status_code}")
        else:
            record("WhatsApp Health Endpoint (/api/whatsapp/health/)", "FAIL", f"Expected 200, got {res_health.status_code}")
    except Exception as e:
        record("WhatsApp Health Endpoint (/api/whatsapp/health/)", "FAIL", str(e))

    # 4. Unauthenticated access enforcement (401 Unauthorized)
    endpoints_to_protect = [
        ("/api/prospects/", "Prospects"),
        ("/api/market-events/", "Market Events"),
        ("/api/whatsapp/session/list/", "WhatsApp Session List"),
        ("/api/digital-marketing/dashboard/", "Digital Marketing Dashboard"),
    ]
    all_protected = True
    for ep, label in endpoints_to_protect:
        try:
            res = client.get(ep)
            if res.status_code != 401:
                all_protected = False
                record(f"Security: {label} ({ep})", "FAIL", f"Expected 401, got {res.status_code}")
        except Exception as e:
            all_protected = False
            record(f"Security: {label} ({ep})", "FAIL", str(e))
    if all_protected:
        record("Security Gate: Protected Endpoints Enforce 401", "PASS", "4/4 endpoints returned 401")

    # 5. Invalid credentials to login endpoint
    try:
        res = client.post(
            "/api/auth/login/",
            {"email": "invalid_user@marketintel.com", "password": "wrong_password!"},
            content_type="application/json",
        )
        if res.status_code == 401:
            record("Auth Gate: Invalid Login Gracefully Rejected", "PASS", f"HTTP {res.status_code}")
        else:
            record("Auth Gate: Invalid Login Gracefully Rejected", "FAIL", f"Expected 401, got {res.status_code}")
    except Exception as e:
        record("Auth Gate: Invalid Login Gracefully Rejected", "FAIL", str(e))

    # 6. Google Auth URL endpoint
    try:
        res = client.get("/api/auth/google/url/")
        if res.status_code == 200 and "url" in res.json():
            record("Google OAuth URL Generation", "PASS", "Valid URL generated")
        else:
            record("Google OAuth URL Generation", "FAIL", f"Status: {res.status_code}")
    except Exception as e:
        record("Google OAuth URL Generation", "FAIL", str(e))

    # 7. Database connectivity & synthetic CRUD cycle
    try:
        test_user = User.objects.create_user(
            username="ci_smoke_user_temp",
            email="ci_smoke@marketintel.com",
            password="TemporaryPassword123!",
        )
        prospect = Prospect.objects.create(
            company_name="CI Smoke Test Corp",
            country_head_office="IN",
            operational_status="Active",
            company_structure="Parent",
            primary_offering_type="Products",
            official_website_url="https://cismoke.example.com",
            created_by="ci_smoke",
        )
        retrieved = Prospect.objects.get(id=prospect.id)
        retrieved_name = retrieved.company_name
        prospect.delete()
        test_user.delete()
        record("Database Connectivity & CRUD Lifecycle", "PASS", f"Verified object lifecycle ({retrieved_name})")
    except Exception as e:
        record("Database Connectivity & CRUD Lifecycle", "FAIL", str(e))

    # 8. Core application model queryability
    try:
        u_count = User.objects.count()
        p_count = Prospect.objects.count()
        e_count = MarketEvent.objects.count()
        w_count = WhatsAppSession.objects.count()
        s_count = SocialPost.objects.count()
        record(
            "Application Models Queryable",
            "PASS",
            f"Users={u_count}, Prospects={p_count}, Events={e_count}, Sessions={w_count}, Posts={s_count}",
        )
    except Exception as e:
        record("Application Models Queryable", "FAIL", str(e))

    # Summary
    print("-" * 60)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    print(f"Smoke Test Summary: Total={len(results)}, Passed={passed}, Failed={failed}")
    print("=" * 60)

    if failed > 0:
        print(f"SMOKE TEST FAILED: {failed} check(s) did not pass.")
        sys.exit(1)
    else:
        print("ALL SMOKE TESTS PASSED.")
        sys.exit(0)

if __name__ == "__main__":
    main()
