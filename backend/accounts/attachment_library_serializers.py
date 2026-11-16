from rest_framework import serializers
from .models import EmailAttachmentLibraryItem


class EmailAttachmentLibraryItemSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = EmailAttachmentLibraryItem
        fields = ['id', 'name', 'file', 'file_url', 'file_size', 'content_type', 'created_at', 'updated_at']
        read_only_fields = ['id', 'file', 'file_url', 'file_size', 'content_type', 'created_at', 'updated_at']

    def get_file_url(self, obj):
        if not obj.file:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url

