from rest_framework import serializers
from django.contrib.auth.models import User
from .models import UserProfile

class UserSerializer(serializers.ModelSerializer):
    role = serializers.ChoiceField(choices=UserProfile.ROLE_CHOICES, source='profile.role', required=False)
    timezone = serializers.CharField(source='profile.timezone', required=False)
    is_superuser = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'password', 'role', 'timezone', 'is_superuser']
        extra_kwargs = {
            'password': {'write_only': True, 'required': False},
            'username': {'required': False} # In case email is used as username
        }

    def to_internal_value(self, data):
        ret = super().to_internal_value(data)
        if isinstance(data, dict) and 'profile' in data and isinstance(data['profile'], dict):
            if 'profile' not in ret:
                ret['profile'] = {}
            if 'role' in data['profile'] and 'role' not in ret['profile']:
                ret['profile']['role'] = data['profile']['role']
            if 'timezone' in data['profile'] and 'timezone' not in ret['profile']:
                ret['profile']['timezone'] = data['profile']['timezone']
        return ret

    def create(self, validated_data):
        profile_data = validated_data.pop('profile', {})
        password = validated_data.pop('password', None)

        # Ensure username is set to email if not provided
        if 'email' in validated_data and not validated_data.get('username'):
            validated_data['username'] = validated_data['email']

        user = User.objects.create(**validated_data)

        if password:
            user.set_password(password)
            user.save()

        # The UserProfile is auto-created by the signal, so we just update it
        if 'role' in profile_data:
            user.profile.role = profile_data['role']
        if 'timezone' in profile_data:
            user.profile.timezone = profile_data['timezone']
        
        if 'role' in profile_data or 'timezone' in profile_data:
            user.profile.save()

        return user

    def update(self, instance, validated_data):
        profile_data = validated_data.pop('profile', {})
        password = validated_data.pop('password', None)

        if 'email' in validated_data and not validated_data.get('username'):
            validated_data['username'] = validated_data['email']

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)

        instance.save()

        if 'role' in profile_data:
            instance.profile.role = profile_data['role']
        if 'timezone' in profile_data:
            instance.profile.timezone = profile_data['timezone']
            
        if 'role' in profile_data or 'timezone' in profile_data:
            instance.profile.save()

        return instance


from .models import MailAccount
import utils.encryption as encryption

class MailAccountSerializer(serializers.ModelSerializer):
    smtp_app_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    imap_app_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    
    class Meta:
        model = MailAccount
        fields = [
            'id', 'name', 'email_address', 'display_name',
            'smtp_host', 'smtp_port', 'smtp_security', 'smtp_username', 'smtp_app_password',
            'imap_host', 'imap_port', 'imap_security', 'imap_username', 'imap_app_password',
            'default_signature', 'is_active', 'last_imap_sync_at', 'last_sync_status', 'last_sync_error'
        ]
        read_only_fields = ['id', 'last_imap_sync_at', 'last_sync_status', 'last_sync_error']

    def create(self, validated_data):
        smtp_pw = validated_data.pop('smtp_app_password', None)
        imap_pw = validated_data.pop('imap_app_password', None)
        
        if smtp_pw:
            validated_data['smtp_app_password_encrypted'] = encryption.encrypt_password(smtp_pw)
        if imap_pw:
            validated_data['imap_app_password_encrypted'] = encryption.encrypt_password(imap_pw)
            
        return super().create(validated_data)

    def update(self, instance, validated_data):
        smtp_pw = validated_data.pop('smtp_app_password', None)
        imap_pw = validated_data.pop('imap_app_password', None)
        
        if smtp_pw:
            validated_data['smtp_app_password_encrypted'] = encryption.encrypt_password(smtp_pw)
        if imap_pw:
            validated_data['imap_app_password_encrypted'] = encryption.encrypt_password(imap_pw)
            
        return super().update(instance, validated_data)


from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.settings import api_settings
from django.contrib.auth.models import update_last_login
from rest_framework import exceptions


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Authenticates existing users via their registered email address and password.
    Supports accounts whose username is identical to their email as well as
    accounts with distinct usernames.
    Normalizes the email address and prevents ambiguous matches.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'] = serializers.CharField(required=False, write_only=True)
        # Keep username optional so existing clients or tests can submit username or email
        if self.username_field in self.fields:
            self.fields[self.username_field].required = False

    def validate(self, attrs):
        raw_identifier = (attrs.get('email') or attrs.get(self.username_field) or '').strip()
        password = attrs.get('password')

        if not raw_identifier or not password:
            raise exceptions.AuthenticationFailed(
                self.error_messages['no_active_account'],
                'no_active_account',
            )

        normalized_email = raw_identifier.lower()

        # Step 1: Look for exact case-insensitive match on registered email
        matching_users = User.objects.filter(email__iexact=normalized_email)
        
        # Step 2: If no match by email, fallback to username (case-insensitive)
        if not matching_users.exists():
            matching_users = User.objects.filter(username__iexact=raw_identifier)
        if not matching_users.exists():
            matching_users = User.objects.filter(username__iexact=normalized_email)

        # Ambiguous matching check: if multiple distinct users match, reject with generic error
        if matching_users.count() > 1:
            raise exceptions.AuthenticationFailed(
                self.error_messages['no_active_account'],
                'no_active_account',
            )

        user = matching_users.first()
        if not user:
            raise exceptions.AuthenticationFailed(
                self.error_messages['no_active_account'],
                'no_active_account',
            )

        # Strictly require correct password and active user status
        if not user.is_active or not user.check_password(password):
            raise exceptions.AuthenticationFailed(
                self.error_messages['no_active_account'],
                'no_active_account',
            )

        self.user = user

        if api_settings.UPDATE_LAST_LOGIN:
            update_last_login(None, self.user)

        refresh = self.get_token(self.user)
        data = {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }
        return data


class GoogleOAuthLoginSerializer(serializers.Serializer):
    code = serializers.CharField(required=True)
    state = serializers.CharField(required=True)


class GmailOAuthCallbackSerializer(serializers.Serializer):
    code = serializers.CharField(required=True)
    state = serializers.CharField(required=True)

