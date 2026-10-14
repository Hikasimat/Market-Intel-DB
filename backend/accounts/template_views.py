from django.db import transaction
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import EmailTemplate, EmailSignatureTemplate
from .template_serializers import EmailTemplateSerializer, EmailSignatureTemplateSerializer


class IsLQOnly(permissions.BasePermission):
    """Lead Qualifier role or superuser."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        profile = getattr(user, 'profile', None)
        return bool(profile and profile.role == 'LQ')


class _OwnedDesignViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsLQOnly]
    model = None

    def get_queryset(self):
        # Owner filtering = object-level isolation; superusers without LQ role can view all
        user = self.request.user
        if user.is_superuser and not (getattr(getattr(user, 'profile', None), 'role', None) == 'LQ'):
            qs = self.model.objects.all()
        else:
            qs = self.model.objects.filter(owner=user)
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

    @action(detail=False, methods=['post'], url_path='upload-image')
    def upload_image(self, request):
        uploaded_file = request.FILES.get('file') or request.FILES.get('image')
        if not uploaded_file:
            return Response({'error': 'No image file uploaded.'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate size (max 5 MB)
        if uploaded_file.size > 5 * 1024 * 1024:
            return Response({'error': 'Image file is too large (max 5 MB).'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate content type
        content_type = getattr(uploaded_file, 'content_type', '') or ''
        allowed_types = {'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml'}
        if content_type.lower() not in allowed_types:
            return Response({'error': 'Unsupported file type. Only JPEG, PNG, GIF, and WebP images are allowed.'}, status=status.HTTP_400_BAD_REQUEST)

        import os, uuid
        from django.conf import settings
        from django.core.files.storage import default_storage

        ext = os.path.splitext(uploaded_file.name)[1].lower() or '.png'
        filename = f"template_images/{uuid.uuid4().hex}{ext}"
        saved_name = default_storage.save(filename, uploaded_file)
        url = default_storage.url(saved_name)

        if not url.startswith(('http://', 'https://')):
            base_url = getattr(settings, 'EMAIL_TRACKING_BASE_URL', '').rstrip('/')
            if base_url and 'trycloudflare.com' not in base_url and not getattr(settings, 'DEBUG', False):
                url = f"{base_url}{url}"
            else:
                url = request.build_absolute_uri(url)

        return Response({'url': url, 'filename': uploaded_file.name}, status=status.HTTP_201_CREATED)

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
