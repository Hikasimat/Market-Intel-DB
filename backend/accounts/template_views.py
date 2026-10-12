from django.db import transaction
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import EmailTemplate, EmailSignatureTemplate
from .template_serializers import EmailTemplateSerializer, EmailSignatureTemplateSerializer


class IsLQOnly(permissions.BasePermission):
    """Strictly Lead Qualifier role (superusers without the LQ role are NOT granted access)."""

    def has_permission(self, request, view):
        user = request.user
        profile = getattr(user, 'profile', None) if user and user.is_authenticated else None
        return bool(profile and profile.role == 'LQ')


class _OwnedDesignViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsLQOnly]
    model = None

    def get_queryset(self):
        # Owner filtering = object-level isolation; other users' ids simply 404.
        qs = self.model.objects.filter(owner=self.request.user)
        q = self.request.query_params.get('search')
        if q:
            qs = qs.filter(name__icontains=q)
        return qs

    def perform_create(self, serializer):
        with transaction.atomic():
            has_any = self.model.objects.filter(owner=self.request.user).exists()
            serializer.save(owner=self.request.user, is_default=not has_any)

    @action(detail=True, methods=['post'], url_path='set-default')
    def set_default(self, request, pk=None):
        obj = self.get_object()
        obj.is_default = True
        obj.save()
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        obj = self.get_object()
        obj.pk = None
        obj.id = __import__('uuid').uuid4()
        obj.name = f"{obj.name} (copy)"[:150]
        obj.is_default = False
        obj._state.adding = True
        obj.save()
        return Response(self.get_serializer(obj).data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        was_default = instance.is_default
        owner = instance.owner
        instance.delete()
        if was_default:
            nxt = self.model.objects.filter(owner=owner).first()
            if nxt:
                nxt.is_default = True
                nxt.save()


class EmailTemplateViewSet(_OwnedDesignViewSet):
    model = EmailTemplate
    serializer_class = EmailTemplateSerializer


class EmailSignatureTemplateViewSet(_OwnedDesignViewSet):
    model = EmailSignatureTemplate
    serializer_class = EmailSignatureTemplateSerializer
