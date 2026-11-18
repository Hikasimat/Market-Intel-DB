from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("knowledge-bases", views.KnowledgeBaseViewSet, basename="rag-knowledge-base")
router.register("session-assignments", views.AssignmentViewSet, basename="rag-session-assignment")

urlpatterns = [
    path("documents/<uuid:pk>/", views.DocumentDetailView.as_view(), name="rag-document-detail"),
    path("documents/<uuid:pk>/retry/", views.DocumentRetryView.as_view(), name="rag-document-retry"),
    path("session-settings/", views.SessionSettingsView.as_view(), name="rag-session-settings"),
    path("session-settings/<str:session_id>/", views.SessionSettingsView.as_view(), name="rag-session-settings-detail"),
    path("test-query/", views.TestQueryView.as_view(), name="rag-test-query"),
    path("health/", views.HealthView.as_view(), name="rag-health"),
    path("", include(router.urls)),
]
