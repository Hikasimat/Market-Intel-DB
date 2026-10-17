from django.db import migrations


def backfill_legacy_tracking(apps, schema_editor):
    """Every email sent before open_tracking_enabled existed carried the pixel.

    Mark them tracked so their historical statistics stay valid and the tracking
    endpoint keeps accepting opens for those already-delivered pixels.
    """
    OutreachEmail = apps.get_model('prospects', 'OutreachEmail')
    OutreachEmail.objects.filter(open_tracking_enabled=False).update(open_tracking_enabled=True)


class Migration(migrations.Migration):

    dependencies = [
        ('prospects', '0041_meeting_client_request_id_meeting_conference_status_and_more'),
    ]

    operations = [
        # Reverse is a no-op: the column is dropped by 0041's reversal anyway.
        migrations.RunPython(backfill_legacy_tracking, migrations.RunPython.noop),
    ]
