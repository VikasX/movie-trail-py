"""The reviewed OpenAPI definitions drive strict DRF input validation and docs."""

from functools import lru_cache

import yaml
from django.conf import settings
from jsonschema import Draft4Validator, FormatChecker
from rest_framework import serializers

from common.errors import APIError


@lru_cache(maxsize=1)
def specification():
    with (settings.BASE_DIR / "docs/openapi.yaml").open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def normalized(item):
    if isinstance(item, list):
        return [normalized(v) for v in item]
    if isinstance(item, dict):
        item = {k: normalized(v) for k, v in item.items()}
        if item.get("nullable") and "type" in item:
            item["type"] = [item["type"], "null"]
    return item


@lru_cache(maxsize=1)
def components():
    return normalized(specification()["components"])


def validate(value, schema):
    # Local refs remain self-contained; no deprecated resolver or network schema lookup.

    validator = Draft4Validator(
        {**normalized(schema), "components": components()},
        format_checker=FormatChecker(),
    )
    errors = sorted(validator.iter_errors(value), key=lambda e: str(list(e.path)))
    if errors:
        fields = {}
        for error in errors:
            name = ".".join(map(str, error.path)) or "non_field_errors"
            # Do not include jsonschema messages that can echo passwords/tokens.
            fields.setdefault(name, []).append("Invalid value or missing/unknown field.")
        raise APIError("validation_error", "Invalid request.", fields=fields)
    return value


class ContractSerializer(serializers.Serializer):
    """Strict nested validation against the existing contract, without schema drift."""

    def __init__(self, *args, schema, **kwargs):
        self.contract_schema = schema
        super().__init__(*args, **kwargs)

    def to_internal_value(self, data):
        if isinstance(data, dict):
            data = dict(data)
            for name in ("email", "display_name", "name"):
                if isinstance(data.get(name), str):
                    data[name] = data[name].strip()
            if isinstance(data.get("email"), str):
                data["email"] = data["email"].casefold()
        return validate(data, self.contract_schema)


def inputs(request, path, method, kwargs):
    operation = specification()["paths"][path][method.lower()]
    properties, required = {}, []
    values = {}
    params = operation.get("parameters", [])
    known = {p["name"] for p in params if p["in"] == "query"}
    if set(request.query_params) - known:
        raise APIError("validation_error", "Unknown query parameter.")
    for p in params:
        if p["in"] not in ("path", "query"):
            continue
        name, schema = p["name"], p["schema"]
        properties[name] = schema
        if p.get("required"):
            required.append(name)
        if p["in"] == "path":
            raw = kwargs[name]
        elif name in request.query_params:
            if len(request.query_params.getlist(name)) != 1:
                raise APIError("validation_error", "Repeated query parameter.")
            raw = request.query_params[name]
        else:
            continue
        try:
            kind = schema.get("type")
            if kind == "integer":
                raw = int(raw)
            elif kind == "number":
                raw = float(raw)
                import math

                if not math.isfinite(raw):
                    raise ValueError
            elif kind == "boolean":
                if raw not in ("true", "false"):
                    raise ValueError
                raw = raw == "true"
            elif kind == "array":
                raw = raw.split(",") if raw else []
        except (ValueError, TypeError):
            raise APIError(
                "validation_error", "Invalid parameter.", fields={name: ["Invalid value."]}
            ) from None
        values[name] = raw
    if path == "/api/v1/shared/{token}/":
        import re

        if not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", values.get("token", "")):
            raise APIError("not_found", "Collection not found.", 404)
    validate(values, {"type": "object", "properties": properties, "required": required})
    body = (
        operation.get("requestBody", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema")
    )
    if body:
        serializer = ContractSerializer(data=request.data, schema=body)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
    else:
        if request.data:
            raise APIError("validation_error", "Request body is not accepted.")
        data = {}
    return operation, values, data
