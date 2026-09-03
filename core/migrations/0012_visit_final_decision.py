from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0011_sync_legacy_verification')]

    operations = [
        migrations.AddField(
            model_name='visit',
            name='final_decision',
            field=models.CharField(blank=True, choices=[('interested', 'Je suis intéressé'), ('thinking', 'Je souhaite réfléchir'), ('not_interested', 'Je ne suis pas intéressé')], max_length=30),
        ),
        migrations.AddField(
            model_name='visit',
            name='final_decision_comment',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='visit',
            name='final_decision_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
