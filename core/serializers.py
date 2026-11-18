# FILE PURPOSE: Describes the JSON fields used by the original health/sample responses.
# Import serializers from rest_framework (DRF request/response helpers).
from rest_framework import serializers

# Import SampleRecord from core.models (the named Python helper module).
from core.models import SampleRecord


class HealthSerializer(serializers.Serializer):
    # Set status: call serializers.ChoiceField with the inputs shown; its definition explains the
    # checks, side effects and return value.
    status = serializers.ChoiceField(choices=["ok"])
    # Set service: call serializers.CharField with the inputs shown; its definition explains the
    # checks, side effects and return value.
    service = serializers.CharField()


class DatabaseHealthSerializer(serializers.Serializer):
    # Set status: call serializers.ChoiceField with the inputs shown; its definition explains the
    # checks, side effects and return value.
    status = serializers.ChoiceField(choices=["ok", "error"])
    # Set database: call serializers.ChoiceField with the inputs shown; its definition explains
    # the checks, side effects and return value.
    database = serializers.ChoiceField(choices=["connected", "unavailable"])


class SampleRecordSerializer(serializers.ModelSerializer):
    # Database-level rules and lookup indexes for the surrounding model, rather than another
    # application table.
    class Meta:
        # Set model: reuse SampleRecord, which was prepared earlier in this function.
        model = SampleRecord
        # fields holds the safe field-to-message mapping that the browser can display. Next, build
        # an ordered list of 3 entries.
        fields = ["id", "name", "message"]
        # Set read_only_fields: reuse fields, which was prepared earlier in this function.
        read_only_fields = fields


class DatabaseUnavailableSerializer(serializers.Serializer):
    # Set detail: call serializers.CharField with the inputs shown; its definition explains the
    # checks, side effects and return value.
    detail = serializers.CharField()
