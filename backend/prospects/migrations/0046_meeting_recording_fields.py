from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('prospects', '0045_meeting_calendar_event_id_meeting_calendar_type_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='meeting',
            name='recording_file',
            field=models.FileField(blank=True, help_text='Downloaded audio/video recording of the meeting from Google Meet.', null=True, upload_to='meeting_recordings/%Y/%m/'),
        ),
        migrations.AddField(
            model_name='meeting',
            name='recording_status',
            field=models.CharField(blank=True, default='NONE', help_text='Status of recording download (NONE, PROCESSING, COMPLETED, FAILED, NOT_FOUND)', max_length=50),
        ),
        migrations.AddField(
            model_name='meeting',
            name='recording_downloaded_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='meeting',
            name='recording_file_size',
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='meeting',
            name='recording_mime_type',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='meeting',
            name='google_conference_record_id',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='meeting',
            name='google_recording_id',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='meeting',
            name='recording_drive_file_id',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
    ]

