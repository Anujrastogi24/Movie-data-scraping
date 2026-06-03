# Generated manually for MovieCinema app updates.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('home', '0004_alter_image_urls'),
    ]

    operations = [
        migrations.AddField(
            model_name='movie',
            name='genres',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AlterField(
            model_name='movie',
            name='cast',
            field=models.TextField(blank=True, max_length=1200),
        ),
        migrations.AlterField(
            model_name='movie',
            name='dLink',
            field=models.TextField(blank=True, max_length=1200),
        ),
        migrations.AlterField(
            model_name='movie',
            name='image',
            field=models.TextField(blank=True, max_length=500),
        ),
        migrations.AlterField(
            model_name='movie',
            name='mLink',
            field=models.TextField(blank=True, max_length=1200),
        ),
        migrations.AlterField(
            model_name='movie',
            name='tLink',
            field=models.TextField(blank=True, max_length=1200),
        ),
    ]
