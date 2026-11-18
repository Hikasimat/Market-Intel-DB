import django.db.models.deletion
from django.db import migrations, models


def _forwards_drop_not_null(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute(
            'ALTER TABLE "prospects_meeting" ALTER COLUMN "prospect_id" DROP NOT NULL;'
        )
    else:
        Meeting = apps.get_model('prospects', 'Meeting')
        Prospect = apps.get_model('prospects', 'Prospect')
        old_field = Meeting._meta.get_field('prospect')
        new_field = models.ForeignKey(
            blank=True,
            null=True,
            on_delete=django.db.models.deletion.CASCADE,
            related_name='meetings',
            to=Prospect,
        )
        new_field.set_attributes_from_name('prospect')
        schema_editor.alter_field(Meeting, old_field, new_field)


class Migration(migrations.Migration):

    dependencies = [
        ('prospects', '0050_pretask'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(_forwards_drop_not_null, reverse_code=migrations.RunPython.noop),
            ],
            state_operations=[
                migrations.AlterField(
                    model_name='meeting',
                    name='prospect',
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='meetings',
                        to='prospects.prospect',
                    ),
                ),
            ],
        ),
    ]
