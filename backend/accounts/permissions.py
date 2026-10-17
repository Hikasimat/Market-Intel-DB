from rest_framework import permissions
from rest_framework.permissions import SAFE_METHODS


class IsPRE(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.user and request.user.is_superuser:
            return True
        return bool(
            request.user and
            request.user.is_authenticated and
            hasattr(request.user, 'profile') and
            request.user.profile.role == 'PRE'
        )


class IsLQ(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.user and request.user.is_superuser:
            return True
        return bool(
            request.user and
            request.user.is_authenticated and
            hasattr(request.user, 'profile') and
            request.user.profile.role == 'LQ'
        )


class IsLQOrManager(permissions.BasePermission):
    """Allows access to LQ, Manager, and Superuser (PRE role strictly excluded)."""
    def has_permission(self, request, view):
        if request.user and request.user.is_superuser:
            return True
        return bool(
            request.user and
            request.user.is_authenticated and
            hasattr(request.user, 'profile') and
            request.user.profile.role in ['LQ', 'MANAGER']
        )


class IsPREOrLQ(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.user and request.user.is_superuser:
            return True
        return bool(
            request.user and
            request.user.is_authenticated and
            hasattr(request.user, 'profile') and
            request.user.profile.role in ['PRE', 'LQ']
        )


class IsManager(permissions.BasePermission):
    """Allows access to Manager role and Superuser."""

    def has_permission(self, request, view):
        if request.user and request.user.is_superuser:
            return True
        return bool(
            request.user and
            request.user.is_authenticated and
            hasattr(request.user, 'profile') and
            request.user.profile.role == 'MANAGER'
        )


class IsManagerOrSuperuser(permissions.BasePermission):
    """Alias for IsManager — both Manager and Superuser allowed."""

    def has_permission(self, request, view):
        if request.user and request.user.is_superuser:
            return True
        return bool(
            request.user and
            request.user.is_authenticated and
            hasattr(request.user, 'profile') and
            request.user.profile.role == 'MANAGER'
        )


class IsManagerReadOnly(permissions.BasePermission):
    """
    Allows Manager (and Superuser) to use safe HTTP methods only.
    Non-safe methods return 403.
    """

    def has_permission(self, request, view):
        if request.user and request.user.is_superuser:
            return True
        if not (request.user and request.user.is_authenticated):
            return False
        role = getattr(getattr(request.user, 'profile', None), 'role', None)
        if role == 'MANAGER':
            return request.method in SAFE_METHODS
        return False


class IsPREOrLQOrManager(permissions.BasePermission):
    """Allows PRE, LQ, Manager, and Superuser."""

    def has_permission(self, request, view):
        if request.user and request.user.is_superuser:
            return True
        return bool(
            request.user and
            request.user.is_authenticated and
            hasattr(request.user, 'profile') and
            request.user.profile.role in ['PRE', 'LQ', 'MANAGER']
        )
