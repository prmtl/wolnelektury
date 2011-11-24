from django.db import models
from django.contrib.auth.models import User
from catalogue.models import Book


class Underline(models.Model):
    book = models.ForeignKey(Book)
    start = models.IntegerField()
    end = models.IntegerField()
    comment = models.TextField(blank=True)
    user = models.ForeignKey(User)
