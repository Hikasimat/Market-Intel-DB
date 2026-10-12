import json

from rest_framework import serializers

from .models import EmailTemplate, EmailSignatureTemplate
from .template_utils import (
    MAX_HTML_BYTES, MAX_PROJECT_BYTES, sanitize_email_html, html_to_text,
)


class _BaseDesignSerializer(serializers.ModelSerializer):
    """Owner is never accepted from the client; HTML is always re-sanitized server side."""

    def validate_name(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('Name is required.')
        return value

    def validate_project_data(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError('project_data must be a JSON object.')
        if len(json.dumps(value)) > MAX_PROJECT_BYTES:
            raise serializers.ValidationError('Editor project data is too large.')
        return value

    def validate_html(self, value):
        value = value or ''
        if len(value.encode('utf-8')) > MAX_HTML_BYTES:
            raise serializers.ValidationError('HTML content is too large.')
        return sanitize_email_html(value)

    def validate(self, attrs):
        if 'html' in attrs:
            # Plain-text version is always derived from the sanitized HTML unless supplied.
            if not attrs.get('text'):
                attrs['text'] = html_to_text(attrs['html'])
        return attrs


class EmailTemplateSerializer(_BaseDesignSerializer):
    class Meta:
        model = EmailTemplate
        fields = ['id', 'name', 'description', 'subject', 'project_data', 'html', 'text',
                  'is_default', 'created_at', 'updated_at']
        read_only_fields = ['id', 'is_default', 'created_at', 'updated_at']


class EmailSignatureTemplateSerializer(_BaseDesignSerializer):
    class Meta:
        model = EmailSignatureTemplate
        fields = ['id', 'name', 'project_data', 'html', 'text',
                  'is_default', 'created_at', 'updated_at']
        read_only_fields = ['id', 'is_default', 'created_at', 'updated_at']
