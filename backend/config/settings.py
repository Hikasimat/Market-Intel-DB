from pathlib import Path
from datetime import timedelta
import os
from dotenv import load_dotenv
import dj_database_url

load_dotenv(override=True)

BASE_DIR = Path(__file__).resolve().parent.parent

# ── Security ──────────────────────────────────────────────────────────────────
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

_default_key = 'django-insecure-default-key-for-dev'
SECRET_KEY = os.getenv('SECRET_KEY', _default_key)
if not DEBUG and SECRET_KEY == _default_key:
    raise ValueError("SECRET_KEY must be set in production!")

ALLOWED_HOSTS = [
    h.strip()
    for h in os.getenv('ALLOWED_HOSTS', '127.0.0.1,localhost,accepting-chef-shoulder-identical.trycloudflare.com').split(',')
    if h.strip()
]

# Trust the proxy (Nginx) HTTPS header so request.is_secure() works correctly.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# ── Applications ──────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_filters',
    'storages',
    'accounts',
    'companies',
    'prospects',
    'market_events',
    'whatsapp',
    'drf_spectacular',
]

# ── Middleware ─────────────────────────────────────────────────────────────────
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# ── Database ──────────────────────────────────────────────────────────────────
# Local development: uses individual DB_* vars.
# Production (EC2 + RDS): uses DATABASE_URL.
_database_url = os.getenv('DATABASE_URL')

if _database_url:
    DATABASES = {
        'default': dj_database_url.config(
            default=_database_url,
            conn_max_age=int(os.environ.get('CONN_MAX_AGE', 600)),
            conn_health_checks=True,
            ssl_require=os.getenv('DB_SSL_REQUIRE', 'true').lower() == 'true',
        )
    }
    # If the user provides an RDS CA bundle path, support verify-full
    _sslrootcert = os.getenv('DB_SSL_ROOT_CERT')
    if _sslrootcert:
        DATABASES['default'].setdefault('OPTIONS', {})
        DATABASES['default']['OPTIONS'].update({
            'sslmode': 'verify-full',
            'sslrootcert': _sslrootcert,
        })
    elif os.getenv('DB_SSL_REQUIRE', 'true').lower() == 'true':
        DATABASES['default'].setdefault('OPTIONS', {})
        DATABASES['default']['OPTIONS'].setdefault('sslmode', 'require')
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DB_NAME', 'marketintel'),
            'USER': os.environ.get('DB_USER', 'postgres'),
            'PASSWORD': os.environ.get('DB_PASSWORD', ''),
            'HOST': os.environ.get('DB_HOST', 'localhost'),
            'PORT': os.environ.get('DB_PORT', '5432'),
            'CONN_MAX_AGE': 0,
            'CONN_HEALTH_CHECKS': True,
        }
    }

# ── Password validation ───────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ── Internationalisation ──────────────────────────────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ── Static files ──────────────────────────────────────────────────────────────
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── DRF + JWT ─────────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'accounts.authentication.CookieJWTAuthentication',
    ),
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Market Intel DB API',
    'DESCRIPTION': 'API Documentation for Market Intel DB',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    # Rotate refresh tokens on each use — old tokens become invalid.
    'ROTATE_REFRESH_TOKENS': False,
    # Blacklist old refresh tokens after rotation to prevent reuse.
    'BLACKLIST_AFTER_ROTATION': False,
    # Update the last login timestamp on token issue.
    'UPDATE_LAST_LOGIN': True,
}

# ── CORS ──────────────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        'CORS_ALLOWED_ORIGINS',
        'http://localhost:5173'
    ).split(',')
    if origin.strip()
]

# Allow cookies (JWT access/refresh) to be sent cross-origin
CORS_ALLOW_CREDENTIALS = True

# ── CSRF ──────────────────────────────────────────────────────────────────────
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        'CSRF_TRUSTED_ORIGINS',
        'http://localhost:5173'
    ).split(',')
    if origin.strip()
]

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    # For cross-origin cookie sharing between Amplify and EC2, SameSite must be None and Secure must be True
    SESSION_COOKIE_SAMESITE = 'None'
    CSRF_COOKIE_SAMESITE = 'None'
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# ── Email open tracking ───────────────────────────────────────────────────────
# Set to the public backend URL in production (e.g. https://YOUR_BACKEND_DOMAIN).
# For local development use http://localhost:8000 or a Cloudflare Quick Tunnel URL.
EMAIL_TRACKING_BASE_URL = os.getenv(
    'EMAIL_TRACKING_BASE_URL', 'http://localhost:8000'
).rstrip('/')

EMAIL_OPEN_TRACKING_ENABLED = (
    os.getenv('EMAIL_OPEN_TRACKING_ENABLED', 'true').lower() == 'true'
)

# Controls how recipient mailbox existence is probed during email verification.
#   mx_only    (default) — syntax + MX only; safe for EC2 / any env where
#                          outbound port 25 is blocked.
#   smtp_local           — direct SMTP port-25 probe; suitable for local dev
#                          where the ISP/network allows outbound port 25.
EMAIL_VERIFICATION_PROVIDER = os.getenv('EMAIL_VERIFICATION_PROVIDER', 'mx_only').strip().lower()

# ── File / Attachment storage ─────────────────────────────────────────────────
# Development: files stored locally in backend/attachments/
# Production:  set USE_OBJECT_STORAGE=true and supply AWS_* / R2 credentials.
if os.getenv('USE_OBJECT_STORAGE', 'false').lower() == 'true':
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
    # If credentials are not provided in environment, boto3 will automatically use the attached EC2 IAM Role.
    _aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
    _aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    if _aws_access_key and _aws_secret_key:
        AWS_ACCESS_KEY_ID = _aws_access_key
        AWS_SECRET_ACCESS_KEY = _aws_secret_key

    AWS_STORAGE_BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME')
    
    _endpoint_url = os.getenv('AWS_S3_ENDPOINT_URL')
    if _endpoint_url:
        AWS_S3_ENDPOINT_URL = _endpoint_url
        
    AWS_S3_REGION_NAME = os.getenv('AWS_S3_REGION_NAME', 'ap-south-1')
    AWS_DEFAULT_ACL = None
    AWS_S3_FILE_OVERWRITE = False
    
    # Enable Server Side Encryption for S3
    AWS_S3_ENCRYPTION = True
    AWS_S3_SIGNATURE_VERSION = 's3v4'

# ── Manager Dashboard Timezone ────────────────────────────────────────────────
# Override via MANAGER_REPORT_TIMEZONE env var (e.g., 'Asia/Kolkata').
# Defaults to Django's TIME_ZONE so the reporting boundary is consistent.
MANAGER_REPORT_TIMEZONE = os.getenv('MANAGER_REPORT_TIMEZONE', TIME_ZONE)

# ── Upload and Request Body Limits ───────────────────────────────────────────
# Django default is 2.5MB (2621440), which causes RequestDataTooBig on rich email
# template payloads and when uploading attachments (which allows up to 25MB).
DATA_UPLOAD_MAX_MEMORY_SIZE = 35 * 1024 * 1024  # 35 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 30 * 1024 * 1024  # 30 MB

# ── Google OAuth & Gmail Configuration ────────────────────────────────────────
GOOGLE_OAUTH_CLIENT_ID = os.getenv('GOOGLE_OAUTH_CLIENT_ID', '').strip()
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv('GOOGLE_OAUTH_CLIENT_SECRET', '').strip()
GOOGLE_OAUTH_REDIRECT_URI = os.getenv(
    'GOOGLE_OAUTH_REDIRECT_URI', 'http://localhost:5173/auth/google/callback'
).strip()
GMAIL_OAUTH_REDIRECT_URI = os.getenv(
    'GMAIL_OAUTH_REDIRECT_URI', 'http://localhost:5173/auth/gmail/callback'
).strip()
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173').strip().rstrip('/')

# Separate, optional Google Calendar authorization (scope: calendar.events only).
CALENDAR_OAUTH_REDIRECT_URI = os.getenv(
    'CALENDAR_OAUTH_REDIRECT_URI', os.getenv('GMAIL_OAUTH_REDIRECT_URI', 'http://localhost:5173/auth/gmail/callback')
).strip()
MEETING_DEFAULT_DURATION_MINUTES = int(os.getenv('MEETING_DEFAULT_DURATION_MINUTES', '30'))




