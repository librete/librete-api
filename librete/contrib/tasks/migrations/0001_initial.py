# Generated by Django 2.0.4 on 2018-04-08 09:54

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('categories', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Task',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated at')),
                ('name', models.CharField(max_length=254, verbose_name='Name')),
                ('start_date', models.DateTimeField(verbose_name='Start date')),
                ('end_date', models.DateTimeField(verbose_name='End date')),
                ('description', models.CharField(blank=True, max_length=1000, verbose_name='Description')),
                ('priority', models.CharField(blank=True, choices=[('high', 'High'), ('medium', 'Medium'), ('low', 'Low')], max_length=254, verbose_name='Priority')),
                ('status', models.CharField(choices=[('active', 'Active'), ('finished', 'Finished')], default='active', max_length=254, verbose_name='Status')),
                ('author', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tasks', to=settings.AUTH_USER_MODEL)),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tasks', to='categories.Category')),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='tasks.Task')),
            ],
            options={
                'verbose_name_plural': 'Tasks',
                'verbose_name': 'Task',
                'ordering': ['created_at'],
            },
        ),
    ]
