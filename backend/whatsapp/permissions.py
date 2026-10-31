"""
backend/whatsapp/permissions.py

Role-based permission classes for the WhatsApp module.

Mapped to existing Market Intel roles:
  SuperAdmin (is_superuser)  → full access
  MANAGER                    → read-only + monitoring + config (no sends)
  LQ                         → send + read (their authorized contacts only)
                               + manage own WhatsApp sessions
  PRE                        → no WhatsApp access

Do not create permissions casually.
Every permission class must have an explicit justification.
"""

from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsSuperAdmin(BasePermission):
    """Super Admin only (Django is_superuser)."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


class CanSendWhatsApp(BasePermission):
    """
    PRE, LQ users and Super Admin can initiate WhatsApp sends.

    MANAGER cannot send messages — they can only view/audit.
    """

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.is_superuser:
            return True
        profile = getattr(request.user, "profile", None)
        return bool(profile and profile.role in ("PRE", "LQ"))


class CanViewWhatsApp(BasePermission):
    """
    PRE, LQ, Manager, and Super Admin can view WhatsApp conversations and messages.
    """

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.is_superuser:
            return True
        profile = getattr(request.user, "profile", None)
        return bool(profile and profile.role in ("PRE", "LQ", "MANAGER"))


class CanManageOwnWhatsAppSession(BasePermission):
    """
    PRE, LQ users and Super Admin can manage their own WhatsApp sessions.

    PRE / LQ users:
      - Register new session names (owned by them).
      - Start/stop their own sessions.
      - View their own sessions.
      - Cannot manage another user's session.

    Super Admin:
      - Can manage any session.
    """

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.is_superuser:
            return True
        profile = getattr(request.user, "profile", None)
        return bool(profile and profile.role in ("PRE", "LQ"))


class CanManageWhatsAppSession(BasePermission):
    """
    Only Super Admin can perform administrative session actions:
    (WAHA-level logout, which disconnects the WhatsApp account itself)

    This is a deliberate higher barrier — unauthorized session logout
    could log out the WhatsApp account entirely.

    For normal start/stop of own sessions, use CanManageOwnWhatsAppSession.
    """

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            profile = getattr(request.user, "profile", None)
            return bool(
                request.user.is_superuser or
                (profile and profile.role in ("PRE", "LQ", "MANAGER"))
            )
        # Write operations (WAHA-level logout) require Super Admin.
        return request.user.is_superuser


class CanManageWhatsAppConfig(BasePermission):
    """
    Manager and Super Admin can change WhatsApp configuration.
    (e.g., enable/disable outbound, change rate limits)
    """

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.is_superuser:
            return True
        profile = getattr(request.user, "profile", None)
        if not profile:
            return False
        if request.method in SAFE_METHODS:
            return profile.role in ("PRE", "LQ", "MANAGER")
        return profile.role == "MANAGER"


class CanResetSafetyStop(BasePermission):
    """
    Only Super Admin can reset the Safety Guard stop.

    This is a deliberate barrier — resuming after a safety stop
    requires conscious Super Admin review, not just Manager action.
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


class CanViewAuditLog(BasePermission):
    """Manager and Super Admin can view the WhatsApp audit log."""

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.is_superuser:
            return True
        profile = getattr(request.user, "profile", None)
        return bool(profile and profile.role == "MANAGER")
