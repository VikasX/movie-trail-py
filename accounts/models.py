from django.conf import settings
from django.db import models


class UserPreferences(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    display_name = models.CharField(max_length=80, blank=True)
    display_language = models.CharField(max_length=20, default="en-US")
    region = models.CharField(max_length=2, default="IN")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{type(self).__name__} {self.pk}"


class AccountToken(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    purpose = models.CharField(max_length=20, choices=[("verify", "verify"), ("reset", "reset")])
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{type(self).__name__} {self.pk}"
