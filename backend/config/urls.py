from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect
from django.conf import settings
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from rest_framework.permissions import IsAdminUser


def redirect_to_frontend(request, route_path=''):
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173').rstrip('/')
    query_string = request.META.get('QUERY_STRING', '')
    target = f"{frontend_url}/{route_path}"
    if query_string:
        target = f"{target}?{query_string}"
    return redirect(target, permanent=False)


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('accounts.urls')),
    path('api/', include('prospects.urls')),
    path('api/', include('market_events.urls')),
    path('api/whatsapp/', include('whatsapp.urls')),
    path('api/digital-marketing/', include('digital_marketing.urls')),

    # Frontend Route Redirection (if OAuth providers callback to backend domain)
    path('digital-marketing/<path:route_path>', redirect_to_frontend),
    path('auth/<path:route_path>', redirect_to_frontend),

    # API Documentation (Restricted to admin users in production)
    path(
        'api/schema/',
        SpectacularAPIView.as_view(
            permission_classes=[IsAdminUser] if not getattr(settings, 'DEBUG', False) else []
        ),
        name='schema',
    ),
    path(
        'api/docs/',
        SpectacularSwaggerView.as_view(
            url_name='schema',
            permission_classes=[IsAdminUser] if not getattr(settings, 'DEBUG', False) else []
        ),
        name='swagger-ui',
    ),
    path(
        'api/redoc/',
        SpectacularRedocView.as_view(
            url_name='schema',
            permission_classes=[IsAdminUser] if not getattr(settings, 'DEBUG', False) else []
        ),
        name='redoc',
    ),
]

from django.conf.urls.static import static

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
