from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0014_googlecalendarcredentials'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='role',
            field=models.CharField(
                choices=[
                    ('PRE', 'Prospect Research Engineer'),
                    ('LQ', 'Lead Qualifier'),
                    ('MANAGER', 'Manager'),
                    ('DM', 'Digital Marketing'),
                ],
                default='PRE',
                max_length=10,
            ),
        ),
    ]
