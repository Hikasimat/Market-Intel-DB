"""
Email verification engine for MarketIntel.

Verification stages:
  1. Syntax validation       — always runs
  2. MX record lookup        — always runs (uses dns.resolver or DoH fallback)
  3. Mailbox-level probe     — only when an external provider is configured
                               OR when running outside serverless (local dev)

Why the split:
  Many hosting providers and serverless environments block all outbound SMTP on port 25.
  Attempting a direct SMTP probe against the recipient MX server often raises OSError / timeout,
  which previously returned UNKNOWN even when the domain/MX were perfectly valid.

  When mx_only is used, the engine returns:
    VALID   → syntax OK + domain has MX records
    INVALID → syntax error OR domain has no MX / does not exist
    UNKNOWN → MX found but mailbox-level probe is unavailable or inconclusive

Environment variables (all optional):
  EMAIL_VERIFICATION_PROVIDER=mx_only|smtp_local
    mx_only     (default) — skip direct SMTP probe; safe for environments blocking port 25
    smtp_local  — attempt direct SMTP port-25 probe; suitable for environments
                  where outbound port 25 is unrestricted

  Future extension: add provider=zerobounce|abstract|mailboxlayer etc.
  to call an HTTPS verification API instead of direct SMTP.
"""

import os
import re
import socket
import smtplib
import dns.resolver
from typing import Any, Dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def verify_email_syntax(email: str) -> bool:
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return re.match(pattern, email) is not None


def _resolve_mx(domain: str):
    """
    Attempt MX lookup via the system resolver.
    Returns a sorted list of dns.rdtypes.ANY.MX.MX records, or raises.
    """
    records = dns.resolver.resolve(domain, 'MX')
    return sorted(records, key=lambda r: r.preference)


def _resolve_mx_doh(domain: str):
    """
    Fallback: resolve MX via Cloudflare DNS-over-HTTPS (port 443/HTTPS).
    Used when the system resolver is unavailable or returns unexpected errors.
    Returns a non-empty list of MX hostnames (strings), or raises ValueError.
    """
    import urllib.request
    import json

    url = f"https://cloudflare-dns.com/dns-query?name={domain}&type=MX"
    req = urllib.request.Request(url, headers={"accept": "application/dns-json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
    except Exception as exc:
        raise ValueError(f"DoH query failed: {exc}") from exc

    answers = data.get("Answer") or []
    mx_hosts = []
    for a in answers:
        if a.get("type") == 15:  # MX record type
            # Value format: "10 aspmx.l.google.com."
            parts = str(a.get("data", "")).split()
            if len(parts) == 2:
                mx_hosts.append(parts[1].rstrip("."))
    if not mx_hosts:
        raise ValueError("No MX records in DoH response")
    return mx_hosts


# ---------------------------------------------------------------------------
# Public engine
# ---------------------------------------------------------------------------

def verify_email_engine(email: str) -> Dict[str, Any]:
    """
    Verify an email address.  Returns a dict compatible with the existing
    EmailVerification model fields.
    """
    result: Dict[str, Any] = {
        'status': 'UNVERIFIED',
        'reason': '',
        'syntax_valid': False,
        'domain_valid': False,
        'mx_found': False,
        'smtp_checked': False,
        'smtp_valid': False,
        'is_disposable': False,
        'is_role_account': False,
        'is_catch_all': False,
    }

    # ── 1. Syntax ────────────────────────────────────────────────────────────
    if not verify_email_syntax(email):
        result['status'] = 'INVALID'
        result['reason'] = 'Invalid email syntax.'
        return result

    result['syntax_valid'] = True

    local_part, domain = email.split('@', 1)

    role_prefixes = {'info', 'admin', 'sales', 'support', 'contact',
                     'hello', 'billing', 'hr', 'noreply', 'no-reply'}
    if local_part.lower() in role_prefixes:
        result['is_role_account'] = True

    # ── 2. MX lookup ─────────────────────────────────────────────────────────
    mail_server = None  # first MX hostname as string, set below if found

    try:
        mx_records = _resolve_mx(domain)
        result['domain_valid'] = True
        result['mx_found'] = True
        mail_server = str(mx_records[0].exchange).rstrip('.')

    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN,
            dns.resolver.NoNameservers):
        # Hard failure — domain does not exist or genuinely has no MX.
        result['status'] = 'INVALID'
        result['reason'] = (
            f"Domain '{domain}' does not exist or has no valid MX records."
        )
        return result

    except dns.exception.Timeout:
        # System resolver timed out — try DoH before giving up.
        try:
            doh_hosts = _resolve_mx_doh(domain)
            result['domain_valid'] = True
            result['mx_found'] = True
            mail_server = doh_hosts[0]
        except Exception as doh_exc:
            result['status'] = 'UNKNOWN'
            result['reason'] = (
                f"DNS lookup timed out and DoH fallback also failed: {doh_exc}"
            )
            return result

    except Exception as exc:
        # Unexpected resolver error — don't mark INVALID.
        result['status'] = 'UNKNOWN'
        result['reason'] = f"DNS lookup failed unexpectedly: {exc}"
        return result

    # ── 3. Mailbox-level probe ────────────────────────────────────────────────
    # Read the verification provider from environment.
    #   mx_only     → skip SMTP probe (safe for restricted environments), returns VALID if MX exists
    #   smtp_local  → attempt direct port-25 SMTP probe (local dev only)
    provider = os.getenv('EMAIL_VERIFICATION_PROVIDER', 'mx_only').strip().lower()

    if provider == 'mx_only':
        # Any environment where port-25 is blocked.
        # MX exists → we know the domain can receive mail. Mailbox-level
        # existence is skipped. We return VALID so the frontend accepts it.
        result['status'] = 'VALID'
        result['reason'] = (
            "Email syntax is valid and the domain has valid MX records. "
            "Individual mailbox existence was not checked."
        )
        return result

    if provider == 'smtp_local':
        # ── Direct SMTP port-25 probe (local development only) ───────────────
        result['smtp_checked'] = True
        try:
            server = smtplib.SMTP(mail_server, 25, timeout=10)
            server.ehlo_or_helo_if_needed()
            code, _ = server.mail('verify@example.com')
            if code >= 400:
                server.quit()
                result['status'] = 'UNKNOWN'
                result['reason'] = f"SMTP server rejected sender probe. Code: {code}"
                return result

            code, resp = server.rcpt(email)
            server.quit()

            if code == 250:
                result['status'] = 'VALID'
                result['smtp_valid'] = True
                result['reason'] = 'Mailbox accepted SMTP verification.'
            elif code >= 500:
                resp_text = resp.decode('utf-8', errors='ignore').lower()
                blocking_keywords = {'policy', 'spamhaus', 'dynamic ip',
                                     'blocked', 'banned'}
                if any(kw in resp_text for kw in blocking_keywords):
                    result['status'] = 'UNKNOWN'
                    result['reason'] = (
                        f"SMTP verification blocked by recipient policy "
                        f"(IP/spam reputation): {code} {resp_text}"
                    )
                else:
                    result['status'] = 'INVALID'
                    result['reason'] = (
                        f"Mailbox rejected. Permanent error: "
                        f"{code} {resp.decode('utf-8', errors='ignore')}"
                    )
            else:
                result['status'] = 'UNKNOWN'
                result['reason'] = (
                    f"SMTP server returned a temporary/ambiguous response. "
                    f"Code: {code}"
                )

        except (socket.timeout, ConnectionRefusedError, OSError):
            result['status'] = 'UNKNOWN'
            result['reason'] = (
                "Mailbox existence could not be reliably determined. "
                "The domain has valid mail servers, but the direct SMTP "
                "connection on port 25 was refused or timed out. "
                "This is normal when outbound port 25 is blocked by the network."
            )
        except Exception as exc:
            result['status'] = 'UNKNOWN'
            result['reason'] = f"Unexpected error during SMTP probe: {exc}"

        return result

    # ── Unknown provider value ────────────────────────────────────────────────
    result['status'] = 'UNKNOWN'
    result['reason'] = (
        f"EMAIL_VERIFICATION_PROVIDER='{provider}' is not recognised. "
        "MX records were found. Configure a supported provider for "
        "mailbox-level verification."
    )
    return result
