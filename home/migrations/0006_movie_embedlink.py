from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('home', '0005_movie_genres_alter_movie_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='movie',
            name='embedLink',
            field=models.TextField(blank=True, max_length=1200),
        ),
    ]
