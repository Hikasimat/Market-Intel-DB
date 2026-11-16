import os
from rest_framework import viewsets, status, permissions
from rest_framework.response import Response
from rest_framework.decorators import action
from django.http import FileResponse, Http404
from .models import EmailAttachmentLibraryItem
from .attachment_library_serializers import EmailAttachmentLibraryItemSerializer

BLOCKED_EXTENSIONS = {'exe', 'bat', 'cmd', 'js', 'ps1', 'vbs', 'scr', 'sh', 'com', 'msi', 'jar'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB per file
MAX_ITEMS_PER_USER = 5


class EmailAttachmentLibraryViewSet(viewsets.ModelViewSet):
    """
    User-managed attachment library endpoints:
    - GET /api/auth/attachment-library/ : list user's saved attachments (up to 5)
    - POST /api/auth/attachment-library/ : upload a new file to the library (max 5)
    - PATCH /api/auth/attachment-library/<id>/ : rename file
    - DELETE /api/auth/attachment-library/<id>/ : delete from library and disk
    - GET /api/auth/attachment-library/<id>/download/ : download file binary
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = EmailAttachmentLibraryItemSerializer

    def get_queryset(self):
        return EmailAttachmentLibraryItem.objects.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        current_count = EmailAttachmentLibraryItem.objects.filter(user=request.user).count()
        if current_count >= MAX_ITEMS_PER_USER:
            return Response(
                {"error": f"Attachment Library limit reached ({MAX_ITEMS_PER_USER} files max). Please delete an existing file to add a new one."},
                status=status.HTTP_400_BAD_REQUEST
            )

        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            return Response(
                {"error": "No file was uploaded. Please provide a file."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if uploaded_file.size > MAX_FILE_SIZE:
            return Response(
                {"error": f"File exceeds the 10MB limit ({(uploaded_file.size / (1024*1024)):.1f}MB)."},
                status=status.HTTP_400_BAD_REQUEST
            )

        filename = uploaded_file.name or 'attachment'
        ext = filename.split('.')[-1].lower() if '.' in filename else ''
        if ext in BLOCKED_EXTENSIONS:
            return Response(
                {"error": f"File type .{ext} is not allowed for email attachments."},
                status=status.HTTP_400_BAD_REQUEST
            )

        name = (request.data.get('name') or filename).strip()
        if not name:
            name = filename

        item = EmailAttachmentLibraryItem.objects.create(
            user=request.user,
            name=name[:255],
            file=uploaded_file,
            file_size=uploaded_file.size,
            content_type=getattr(uploaded_file, 'content_type', '') or 'application/octet-stream',
        )

        serializer = self.get_serializer(item)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        if instance.file:
            try:
                instance.file.delete(save=False)
            except Exception:
                pass
        instance.delete()

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        item = self.get_object()
        if not item.file:
            raise Http404("File not found on storage")
        try:
            response = FileResponse(
                item.file.open('rb'),
                content_type=item.content_type or 'application/octet-stream'
            )
            response['Content-Disposition'] = f'attachment; filename="{item.name}"'
            return response
        except (FileNotFoundError, ValueError):
            raise Http404("File not found on server")

