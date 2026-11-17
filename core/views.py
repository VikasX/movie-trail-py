import logging

from django.db import DatabaseError, connection
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import SampleRecord
from core.serializers import (
    DatabaseHealthSerializer,
    DatabaseUnavailableSerializer,
    HealthSerializer,
    SampleRecordSerializer,
)

logger = logging.getLogger(__name__)


@method_decorator(never_cache, name="dispatch")
class HealthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    http_method_names = ["get", "head", "options"]

    @extend_schema(responses=HealthSerializer, tags=["Health"], auth=[])
    def get(self, request):
        return Response({"status": "ok", "service": "CineScope API"})


@method_decorator(never_cache, name="dispatch")
class DatabaseHealthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    http_method_names = ["get", "head", "options"]

    @extend_schema(
        responses={200: DatabaseHealthSerializer, 503: DatabaseHealthSerializer},
        tags=["Health"],
        auth=[],
    )
    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                if cursor.fetchone() != (1,):
                    raise DatabaseError("Unexpected database health result")
        except DatabaseError:
            # Database exception strings can contain connection details; never log them here.
            logger.warning("Database health check failed")
            return Response(
                {"status": "error", "database": "unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"status": "ok", "database": "connected"})


@method_decorator(never_cache, name="dispatch")
class SampleRecordView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    http_method_names = ["get", "head", "options"]

    @extend_schema(
        responses={200: SampleRecordSerializer(many=True), 503: DatabaseUnavailableSerializer},
        tags=["Sample"],
        auth=[],
    )
    def get(self, request):
        try:
            # A bounded public demo read; no writes or seeding during requests.
            data = SampleRecordSerializer(SampleRecord.objects.all()[:20], many=True).data
        except DatabaseError:
            logger.warning("Sample data query failed")
            return Response(
                {"detail": "Database unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(data)
