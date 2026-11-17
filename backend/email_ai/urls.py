from django.urls import path
from .views import (
    generate_personalized_email_view,
    manager_daily_email_report,
    manager_daily_email_report_refresh,
    manager_email_activity_detail,
    manager_email_activity_list,
    manager_email_summary_refresh,
)

urlpatterns = [
    # Personalized Email AI Generation (Outreach, Inbox Compose, Bulk Campaign)
    path("email-ai/generate/", generate_personalized_email_view, name="email-ai-generate"),

    # Manager Email Activity & Daily Email AI Report Routes
    path("manager-dashboard/daily-email-report/", manager_daily_email_report, name="manager-daily-email-report"),
    path("manager-dashboard/daily-email-report/<int:user_id>/refresh/", manager_daily_email_report_refresh, name="manager-daily-email-report-refresh"),
    path("manager-dashboard/email-activity/", manager_email_activity_list, name="manager-email-activity-list"),
    path("manager-dashboard/email-activity/<uuid:thread_id>/", manager_email_activity_detail, name="manager-email-activity-detail"),
    path("manager-dashboard/email-activity/<uuid:thread_id>/refresh-summary/", manager_email_summary_refresh, name="manager-email-summary-refresh"),
]
