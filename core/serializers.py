from rest_framework import serializers

from core.models import SampleRecord


class HealthSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["ok"])
    service = serializers.CharField()


class DatabaseHealthSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["ok", "error"])
    database = serializers.ChoiceField(choices=["connected", "unavailable"])


class SampleRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = SampleRecord
        fields = ["id", "name", "message"]
        read_only_fields = fields


class DatabaseUnavailableSerializer(serializers.Serializer):
    detail = serializers.CharField()
