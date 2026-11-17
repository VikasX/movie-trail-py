import hashlib
import time
import uuid
from contextlib import contextmanager
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from catalog.models import CacheLease
from common.errors import APIError


@contextmanager
def lease(key):
    key = hashlib.sha256(key.encode()).hexdigest()
    owner = uuid.uuid4()
    acquired = False
    for _ in range(10):
        with transaction.atomic():
            CacheLease.objects.filter(key=key, expires_at__lt=timezone.now()).delete()
            try:
                with transaction.atomic():
                    CacheLease.objects.create(
                        key=key, owner=owner, expires_at=timezone.now() + timedelta(seconds=20)
                    )
                acquired = True
            except IntegrityError:
                pass
        if acquired:
            break
        time.sleep(0.05)
    if not acquired:
        raise APIError(
            "service_unavailable",
            "Metadata refresh in progress; retry shortly.",
            503,
            retry_after=1,
        )
    try:
        yield
    finally:
        CacheLease.objects.filter(key=key, owner=owner).delete()
