# Generated by Django 4.1.3 on 2023-01-11 19:40

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('home', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='movie',
            name='dLink',
            field=models.TextField(default=django.utils.timezone.now, max_length=1200),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='movie',
            name='mLink',
            field=models.TextField(default=django.utils.timezone.now, max_length=1200),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='movie',
            name='tLink',
            field=models.TextField(default=django.utils.timezone.now, max_length=1200),
            preserve_default=False,
        ),
    ]