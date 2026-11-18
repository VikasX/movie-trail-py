# FILE PURPOSE: Original health and sample endpoints. Product features live in the other apps.
# Import logging so the code below can use that module namespace.
import logging

# Import DatabaseError, connection from django.db (Django framework/database/security helpers).
from django.db import DatabaseError, connection

# Import method_decorator from django.utils.decorators (Django framework/database/security
# helpers).
from django.utils.decorators import method_decorator

# Import never_cache from django.views.decorators.cache (Django framework/database/security
# helpers).
from django.views.decorators.cache import never_cache

# Import extend_schema from drf_spectacular.utils (the named Python helper module).
from drf_spectacular.utils import extend_schema

# Import status from rest_framework (DRF request/response helpers).
from rest_framework import status

# Import AllowAny from rest_framework.permissions (DRF request/response helpers).
from rest_framework.permissions import AllowAny

# Import Response from rest_framework.response (DRF request/response helpers).
from rest_framework.response import Response

# Import APIView from rest_framework.views (DRF request/response helpers).
from rest_framework.views import APIView

# Import SampleRecord from core.models (the named Python helper module).
from core.models import SampleRecord

# Import DatabaseHealthSerializer, DatabaseUnavailableSerializer, HealthSerializer,
# SampleRecordSerializer from core.serializers (the named Python helper module).
from core.serializers import (
    DatabaseHealthSerializer,
    DatabaseUnavailableSerializer,
    HealthSerializer,
    SampleRecordSerializer,
)

# Set logger: call logging.getLogger with the inputs shown; its definition explains the checks,
# side effects and return value.
logger = logging.getLogger(__name__)


@method_decorator(never_cache, name="dispatch")
class HealthView(APIView):
    # Set authentication_classes: build an ordered list of 0 entries.
    authentication_classes = []
    # Set permission_classes: build an ordered list of 1 entries.
    permission_classes = [AllowAny]
    # Set http_method_names: build an ordered list of 3 entries.
    http_method_names = ["get", "head", "options"]

    # Return fixed process-health JSON; no database or TMDB is queried.
    @extend_schema(responses=HealthSerializer, tags=["Health"], auth=[])
    def get(self, request):
        # INPUTS TO THIS FUNCTION: self = this class instance; request = current browser/user
        # context.
        # Return the result to the caller: call Response with the inputs shown; its definition
        # explains the checks, side effects and return value.
        return Response({"status": "ok", "service": "CineScope API"})


@method_decorator(never_cache, name="dispatch")
class DatabaseHealthView(APIView):
    # Set authentication_classes: build an ordered list of 0 entries.
    authentication_classes = []
    # Set permission_classes: build an ordered list of 1 entries.
    permission_classes = [AllowAny]
    # Set http_method_names: build an ordered list of 3 entries.
    http_method_names = ["get", "head", "options"]

    # Execute a real database SELECT 1 and return only a safe success/failure message.
    @extend_schema(
        responses={200: DatabaseHealthSerializer, 503: DatabaseHealthSerializer},
        tags=["Health"],
        auth=[],
    )
    def get(self, request):
        # INPUTS TO THIS FUNCTION: self = this class instance; request = current browser/user
        # context.
        # Attempt this block; the following except branches handle expected failures without
        # continuing the success path.
        try:
            # Use connection.cursor() for this block; the context manager performs its
            # exit/cleanup when the block ends.
            with connection.cursor() as cursor:
                # Call cursor.execute with the inputs shown; its definition explains the checks,
                # side effects and return value.
                cursor.execute("SELECT 1")
                # Enter this branch only when cursor.fetchone() != (1,). Otherwise execution uses
                # its alternative or continues below.
                if cursor.fetchone() != (1,):
                    # Raise DatabaseError; normal execution of this block stops here.
                    raise DatabaseError("Unexpected database health result")
        # Handle DatabaseError here. The original exception is not automatically safe to expose to
        # the client.
        except DatabaseError:
            # Database exception strings can contain connection details; never log them here.
            # Call logger.warning with the inputs shown; its definition explains the checks, side
            # effects and return value.
            logger.warning("Database health check failed")
            # Return the result to the caller: call Response with the inputs shown; its definition
            # explains the checks, side effects and return value.
            return Response(
                {"status": "error", "database": "unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        # Return the result to the caller: call Response with the inputs shown; its definition
        # explains the checks, side effects and return value.
        return Response({"status": "ok", "database": "connected"})


@method_decorator(never_cache, name="dispatch")
class SampleRecordView(APIView):
    # Set authentication_classes: build an ordered list of 0 entries.
    authentication_classes = []
    # Set permission_classes: build an ordered list of 1 entries.
    permission_classes = [AllowAny]
    # Set http_method_names: build an ordered list of 3 entries.
    http_method_names = ["get", "head", "options"]

    # Read up to twenty real sample rows; this is a smoke test, not movie discovery.
    @extend_schema(
        responses={200: SampleRecordSerializer(many=True), 503: DatabaseUnavailableSerializer},
        tags=["Sample"],
        auth=[],
    )
    def get(self, request):
        # INPUTS TO THIS FUNCTION: self = this class instance; request = current browser/user
        # context.
        # Attempt this block; the following except branches handle expected failures without
        # continuing the success path.
        try:
            # A bounded public demo read; no writes or seeding during requests.
            # data holds the cleaned submitted JSON body (or, in normalization helpers, the
            # upstream object being translated). Next, read
            # SampleRecordSerializer(SampleRecord.objects.all()[:20], many=True).data from the
            # indicated object.
            data = SampleRecordSerializer(SampleRecord.objects.all()[:20], many=True).data
        # Handle DatabaseError here. The original exception is not automatically safe to expose to
        # the client.
        except DatabaseError:
            # Call logger.warning with the inputs shown; its definition explains the checks, side
            # effects and return value.
            logger.warning("Sample data query failed")
            # Return the result to the caller: call Response with the inputs shown; its definition
            # explains the checks, side effects and return value.
            return Response(
                {"detail": "Database unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        # Return the result to the caller: call Response with the inputs shown; its definition
        # explains the checks, side effects and return value.
        return Response(data)
