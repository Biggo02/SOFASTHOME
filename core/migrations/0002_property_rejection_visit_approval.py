from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies=[('core','0001_initial')]
    operations=[
        migrations.AddField(model_name='property',name='rejection_reason',field=models.TextField(blank=True)),
        migrations.AddField(model_name='visit',name='scheduled_date',field=models.DateField(blank=True,null=True)),
        migrations.AddField(model_name='visit',name='scheduled_time',field=models.TimeField(blank=True,null=True)),
        migrations.AddField(model_name='visit',name='owner_approved',field=models.BooleanField(default=False)),
        migrations.AddField(model_name='visit',name='agent_approved',field=models.BooleanField(default=False)),
        migrations.AddField(model_name='visit',name='observation',field=models.TextField(blank=True)),
        migrations.AddField(model_name='visit',name='agent',field=models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,related_name='assigned_visits',to='auth.user')),
    ]
