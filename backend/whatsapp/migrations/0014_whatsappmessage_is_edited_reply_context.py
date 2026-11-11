from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("whatsapp", "0013_whatsappcallrecording"),
    ]

    operations = [
        migrations.AddField(
            model_name="whatsappmessage",
            name="is_edited",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="whatsappmessage",
            name="reply_context",
            field=models.JSONField(
                blank=True,
                help_text="Quoted message preview: {id, body, sender, from_me}.",
                null=True,
            ),
        ),
    ]

