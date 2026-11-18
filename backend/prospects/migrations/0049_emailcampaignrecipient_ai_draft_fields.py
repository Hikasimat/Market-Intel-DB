from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("prospects", "0048_meeting_cbe_delivery_id_meeting_cbe_meeting_id_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="emailcampaignrecipient",
            name="section_number",
            field=models.PositiveIntegerField(db_index=True, default=1),
        ),
        migrations.AddField(
            model_name="emailcampaignrecipient",
            name="custom_subject",
            field=models.CharField(blank=True, default="", max_length=512),
        ),
        migrations.AddField(
            model_name="emailcampaignrecipient",
            name="custom_body",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="emailcampaignrecipient",
            name="outreach_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name="emailcampaignrecipient",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Draft"),
                    ("PENDING", "Pending"),
                    ("SENDING", "Sending"),
                    ("SENT", "Sent"),
                    ("RETRY_PENDING", "Retry Pending"),
                    ("FAILED", "Failed"),
                ],
                default="PENDING",
                max_length=50,
            ),
        ),
    ]
