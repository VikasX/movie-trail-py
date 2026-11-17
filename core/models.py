from django.db import models


class SampleRecord(models.Model):
    """Public demonstration data used to verify reads through the Django ORM."""

    name = models.CharField(max_length=100, unique=True)
    message = models.CharField(max_length=255)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.name
