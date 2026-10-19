from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ProspectViewSet, LQPipelineViewSet, CallbackReminderViewSet, MeetingViewSet,
    ProspectContactViewSet, CommunicationActivityViewSet, CallActivityViewSet,
    OutreachEmailViewSet, EmailTrackingView, EmailLinkClickTrackingView,
    pre_dashboard_stats, AuditReverificationRequestViewSet, GovernmentEntityViewSet,
    EmailCampaignViewSet
)
from .verification_views import EmailVerificationViewSet
from .manager_views import manager_dashboard

router = DefaultRouter()
router.register(r'government-entities', GovernmentEntityViewSet, basename='government-entities')
router.register(r'audit-reverifications', AuditReverificationRequestViewSet, basename='audit-reverifications')
router.register(r'prospects', ProspectViewSet, basename='prospect')
router.register(r'lq-pipeline', LQPipelineViewSet, basename='lq-pipeline')
router.register(r'reminders', CallbackReminderViewSet, basename='reminders')
router.register(r'meetings', MeetingViewSet, basename='meetings')

router.register(r'key-contacts', ProspectContactViewSet, basename='key-contacts')
router.register(r'outreach/communications', CommunicationActivityViewSet, basename='communications')
router.register(r'outreach/calls', CallActivityViewSet, basename='outreach-calls')
router.register(r'outreach/emails', OutreachEmailViewSet, basename='outreach-emails')
router.register(r'email-campaigns', EmailCampaignViewSet, basename='email-campaigns')
router.register(r'email-verifications', EmailVerificationViewSet, basename='email-verifications')

urlpatterns = [
    path('email-tracking/<uuid:tracking_token>/', EmailTrackingView.as_view(), name='email-tracking'),
    path('email-tracking/click/<uuid:tracking_token>/', EmailLinkClickTrackingView.as_view(), name='email-click-tracking'),
    path('pre-dashboard-stats/', pre_dashboard_stats, name='pre-dashboard-stats'),
    path('manager-dashboard/', manager_dashboard, name='manager-dashboard'),
    path('', include(router.urls)),
]
