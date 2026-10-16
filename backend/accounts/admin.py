from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import UserProfile
from django import forms

class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'profile'
    exclude = ('mail_account',)



class CustomUserCreationForm(forms.ModelForm):
    email = forms.EmailField(
        required=True,
        help_text="Required. Primary email address used for login and Google OAuth matching."
    )
    username = forms.CharField(
        required=False,
        help_text="Optional. Defaults to the email address if left blank."
    )
    first_name = forms.CharField(required=False)
    last_name = forms.CharField(required=False)
    role = forms.ChoiceField(
        choices=UserProfile.ROLE_CHOICES,
        initial='PRE',
        required=True,
        help_text="Select user role: PRE, LQ, or MANAGER."
    )
    password = forms.CharField(
        widget=forms.PasswordInput,
        required=True,
        help_text="Set account password."
    )
    
    class Meta:
        model = User
        fields = ('email', 'username', 'first_name', 'last_name', 'role', 'password')

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if not email:
            raise forms.ValidationError("Email address is required.")
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("A user with this email address already exists.")
        return email

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        email = self.cleaned_data.get('email', '').strip().lower()
        if not username:
            username = email
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("A user with this username already exists.")
        return username

    def save(self, commit=True):
        user = super().save(commit=False)
        email = self.cleaned_data['email']
        username = self.cleaned_data['username']
        user.email = email
        user.username = username
        user.first_name = self.cleaned_data.get('first_name', '')
        user.last_name = self.cleaned_data.get('last_name', '')
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
            role = self.cleaned_data.get('role', 'PRE')
            if hasattr(user, 'profile'):
                user.profile.role = role
                user.profile.save()
            else:
                UserProfile.objects.create(user=user, role=role)
        return user

class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)
    list_display = ('username', 'email', 'get_role', 'first_name', 'last_name', 'is_staff', 'is_active')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'profile__role')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('-date_joined',)
    add_form_template = None

    def get_role(self, obj):
        return obj.profile.role if hasattr(obj, 'profile') else '-'
    get_role.short_description = 'Role'
    
    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs['form'] = CustomUserCreationForm
        return super().get_form(request, obj, **kwargs)

    def get_inline_instances(self, request, obj=None):
        if not obj:
            return []
        return super().get_inline_instances(request, obj)
        
    def get_fieldsets(self, request, obj=None):
        if not obj:
            return (
                (None, {
                    'classes': ('wide',),
                    'fields': ('email', 'username', 'first_name', 'last_name', 'role', 'password'),
                }),
            )
        return super().get_fieldsets(request, obj)

# Re-register UserAdmin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)

from .models import GoogleMailCredentials

class GoogleMailCredentialsAdmin(admin.ModelAdmin):
    list_display = ('user', 'email', 'is_active', 'token_expiry', 'updated_at')
    readonly_fields = ('access_token_encrypted', 'refresh_token_encrypted', 'created_at', 'updated_at')
    search_fields = ('user__username', 'email')

admin.site.register(GoogleMailCredentials, GoogleMailCredentialsAdmin)

class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'timezone')
    filter_horizontal = ('whatsapp_sessions',)
    exclude = ('mail_account',)

admin.site.register(UserProfile, UserProfileAdmin)
