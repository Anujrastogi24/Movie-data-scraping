from django.db import models

# Create your models here.
class Movie(models.Model):
    Title = models.CharField(max_length=100)
    description = models.TextField(max_length=1000)
    image = models.TextField(max_length=500)
    cast= models.TextField(max_length=500)
    mLink = models.TextField(max_length=1200)
    tLink = models.URLField(max_length=1200)
    dLink = models.TextField(max_length=1200)


    def __str__(self):
        return self.Title

class Image(models.Model):
    name = models.CharField(max_length=50)
    urls = models.CharField(max_length=300)
    def __str__(self):
        return self.name

        
    