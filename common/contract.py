# FILE PURPOSE: Reads OpenAPI and checks incoming values. This project uses contract-backed
# validation deliberately.
# LEARNING TIP: read the matching walkthrough in docs/BACKEND_GUIDE.md, then follow the block
# comments below.
"""The reviewed OpenAPI definitions drive strict DRF input validation and docs."""

# Import lru_cache from functools (the named Python helper module).
from functools import lru_cache

# Import yaml so the code below can use that module namespace.
import yaml

# Import settings from django.conf (Django framework/database/security helpers).
from django.conf import settings

# Import Draft4Validator, FormatChecker from jsonschema (contract-shape validation).
from jsonschema import Draft4Validator, FormatChecker

# Import serializers from rest_framework (DRF request/response helpers).
from rest_framework import serializers

# Import APIError from common.errors (our shared API layer).
from common.errors import APIError


# Load the YAML contract once per Python process; this caches schema definitions, not user data.
@lru_cache(maxsize=1)
def specification():
    # Use (settings.BASE_DIR / 'docs/openapi.yaml').open(encoding='utf-8') for this block; the
    # context manager performs its exit/cleanup when the block ends.
    with (settings.BASE_DIR / "docs/openapi.yaml").open(encoding="utf-8") as stream:
        # Return the result to the caller: call yaml.safe_load with the inputs shown; its
        # definition explains the checks, side effects and return value.
        return yaml.safe_load(stream)


# Recursively translate OpenAPI nullable fields into the form the JSON validator understands.
def normalized(item):
    # INPUTS TO THIS FUNCTION: item = argument supplied by the caller.
    # Enter this branch only when isinstance(item, list). Otherwise execution uses its alternative
    # or continues below.
    if isinstance(item, list):
        # Return the result to the caller: build a list for each v in item.
        return [normalized(v) for v in item]
    # Enter this branch only when isinstance(item, dict). Otherwise execution uses its alternative
    # or continues below.
    if isinstance(item, dict):
        # Set item: build a lookup dictionary for each (k, v) in item.items().
        item = {k: normalized(v) for k, v in item.items()}
        # Enter this branch only when item.get('nullable') and 'type' in item. Otherwise execution
        # uses its alternative or continues below.
        if item.get("nullable") and "type" in item:
            # Set item['type']: build an ordered list of 2 entries.
            item["type"] = [item["type"], "null"]
    # Return the result to the caller: reuse item, which was prepared earlier in this function.
    return item


# Keep the reusable, converted schema definitions ready for subsequent input checks.
@lru_cache(maxsize=1)
def components():
    # Return the result to the caller: call normalized with the inputs shown; its definition
    # explains the checks, side effects and return value.
    return normalized(specification()["components"])


# Check a value against a schema; report safe field errors without echoing passwords or tokens.
def validate(value, schema):
    # Local refs remain self-contained; no deprecated resolver or network schema lookup.

    # INPUTS TO THIS FUNCTION: value = item being checked; schema = validation rules.
    # validator holds the JSON Schema checker with shared local component definitions attached.
    # Next, call Draft4Validator with the inputs shown; its definition explains the checks, side
    # effects and return value.
    validator = Draft4Validator(
        {**normalized(schema), "components": components()},
        format_checker=FormatChecker(),
    )
    # errors holds validation failures, sorted so the returned field errors have a predictable
    # order. Next, return a separately sorted sequence, leaving the original collection unchanged.
    errors = sorted(validator.iter_errors(value), key=lambda e: str(list(e.path)))
    # Enter this branch only when errors. Otherwise execution uses its alternative or continues
    # below.
    if errors:
        # fields holds the safe field-to-message mapping that the browser can display. Next, build
        # a dictionary with named fields.
        fields = {}
        # Repeat the following block for each error from errors. Each iteration handles that one
        # item/pair.
        for error in errors:
            # name holds a display name or field label; collection names are trimmed and checked
            # for allowed length. Next, evaluate '.'.join(map(str, error.path)) or
            # 'non_field_errors'.
            name = ".".join(map(str, error.path)) or "non_field_errors"
            # Do not include jsonschema messages that can echo passwords/tokens.
            # Add one item at the end of this list.
            fields.setdefault(name, []).append("Invalid value or missing/unknown field.")
        # Stop this action with safe API error 'validation_error' (HTTP 400). The common handler
        # builds its JSON envelope.
        raise APIError("validation_error", "Invalid request.", fields=fields)
    # Return the result to the caller: reuse value, which was prepared earlier in this function.
    return value


# A DRF serializer that validates against the existing OpenAPI schema instead of duplicating
# field definitions.
class ContractSerializer(serializers.Serializer):
    """Strict nested validation against the existing contract, without schema drift."""

    # Keep the chosen schema on this serializer instance before DRF handles the submitted data.
    def __init__(self, *args, schema, **kwargs):
        # INPUTS TO THIS FUNCTION: self = this class instance.
        # Set self.contract_schema: reuse schema, which was prepared earlier in this function.
        self.contract_schema = schema
        # Call super().__init__ with the inputs shown; its definition explains the checks, side
        # effects and return value.
        super().__init__(*args, **kwargs)

    # Trim human-entered text and normalize emails before validating the submitted JSON.
    def to_internal_value(self, data):
        # INPUTS TO THIS FUNCTION: self = this class instance; data = validated JSON.
        # Enter this branch only when isinstance(data, dict). Otherwise execution uses its
        # alternative or continues below.
        if isinstance(data, dict):
            # data holds the cleaned submitted JSON body (or, in normalization helpers, the
            # upstream object being translated). Next, make a dictionary copy so changes here need
            # not mutate the caller dictionary.
            data = dict(data)
            # Repeat the following block for each name from ('email', 'display_name', 'name').
            # Each iteration handles that one item/pair.
            for name in ("email", "display_name", "name"):
                # Enter this branch only when isinstance(data.get(name), str). Otherwise execution
                # uses its alternative or continues below.
                if isinstance(data.get(name), str):
                    # Set data[name]: call data[name].strip with the inputs shown; its definition
                    # explains the checks, side effects and return value.
                    data[name] = data[name].strip()
            # Enter this branch only when isinstance(data.get('email'), str). Otherwise execution
            # uses its alternative or continues below.
            if isinstance(data.get("email"), str):
                # Set data['email']: call data['email'].casefold with the inputs shown; its
                # definition explains the checks, side effects and return value.
                data["email"] = data["email"].casefold()
        # Return the result to the caller: call validate with the inputs shown; its definition
        # explains the checks, side effects and return value.
        return validate(data, self.contract_schema)


# Separate URL/query values from JSON body, convert their types and reject undocumented input.
def inputs(request, path, method, kwargs):
    # Look up the exact endpoint/method, such as paths[/api/v1/titles/][get], in our YAML.
    # INPUTS TO THIS FUNCTION: request = current browser/user context; path = argument supplied by
    # the caller; method = argument supplied by the caller; kwargs = argument supplied by the
    # caller.
    # operation holds the exact method/path definition loaded from the OpenAPI contract. Next,
    # read the entry indexed by method.lower() from specification()['paths'][path].
    operation = specification()["paths"][path][method.lower()]
    # Set (properties, required): keep these related values together as a tuple: {}, [].
    properties, required = {}, []
    # values holds the chosen locale/region or the converted input values passed to later
    # validation. Next, build a dictionary with named fields.
    values = {}
    # params holds path/query settings; this name can also mean outbound TMDB parameters inside
    # catalogue helpers. Next, look up a named setting/value or make the indicated GET call; the
    # surrounding object determines which.
    params = operation.get("parameters", [])
    # Only the documented query names are accepted; a typo is an error, not an ignored filter.
    # known holds a set of documented query names, used to detect typos or unsupported options.
    # Next, build a set of distinct values for each p in params; keep only entries passing p['in']
    # == 'query'.
    known = {p["name"] for p in params if p["in"] == "query"}
    # Enter this branch only when set(request.query_params) - known. Otherwise execution uses its
    # alternative or continues below.
    if set(request.query_params) - known:
        # Stop this action with safe API error 'validation_error' (HTTP 400). The common handler
        # builds its JSON envelope.
        raise APIError("validation_error", "Unknown query parameter.")
    # Repeat the following block for each p from params. Each iteration handles that one
    # item/pair.
    for p in params:
        # Enter this branch only when p['in'] not in ('path', 'query'). Otherwise execution uses
        # its alternative or continues below.
        if p["in"] not in ("path", "query"):
            # Skip the rest of this iteration and move to the next item or allowed retry.
            continue
        # Set (name, schema): keep these related values together as a tuple: p['name'],
        # p['schema'].
        name, schema = p["name"], p["schema"]
        # Set properties[name]: reuse schema, which was prepared earlier in this function.
        properties[name] = schema
        # Enter this branch only when p.get('required'). Otherwise execution uses its alternative
        # or continues below.
        if p.get("required"):
            # Add one item at the end of this list.
            required.append(name)
        # Enter this branch only when p['in'] == 'path'. Otherwise execution uses its alternative
        # or continues below.
        if p["in"] == "path":
            # raw holds the source value before this step converts or normalizes it. Next, read
            # the entry indexed by name from kwargs.
            raw = kwargs[name]
        # Enter this branch only when name in request.query_params. Otherwise execution uses its
        # alternative or continues below.
        elif name in request.query_params:
            # Enter this branch only when len(request.query_params.getlist(name)) != 1. Otherwise
            # execution uses its alternative or continues below.
            if len(request.query_params.getlist(name)) != 1:
                # Stop this action with safe API error 'validation_error' (HTTP 400). The common
                # handler builds its JSON envelope.
                raise APIError("validation_error", "Repeated query parameter.")
            # raw holds the source value before this step converts or normalizes it. Next, read
            # the entry indexed by name from request.query_params.
            raw = request.query_params[name]
        else:
            # Skip the rest of this iteration and move to the next item or allowed retry.
            continue
        # Query strings are text. Convert numbers/booleans/arrays before checking their rules.
        # Attempt this block; the following except branches handle expected failures without
        # continuing the success path.
        try:
            # kind holds the expected JSON type declared by the schema. Next, look up a named
            # setting/value or make the indicated GET call; the surrounding object determines
            # which.
            kind = schema.get("type")
            # Enter this branch only when kind == 'integer'. Otherwise execution uses its
            # alternative or continues below.
            if kind == "integer":
                # raw holds the source value before this step converts or normalizes it. Next,
                # convert to a whole number; invalid text raises an error handled by the
                # surrounding code.
                raw = int(raw)
            # Enter this branch only when kind == 'number'. Otherwise execution uses its
            # alternative or continues below.
            elif kind == "number":
                # raw holds the source value before this step converts or normalizes it. Next,
                # convert to a decimal number before validating its allowed range.
                raw = float(raw)
                # Import math so the code below can use that module namespace.
                import math

                # Enter this branch only when not math.isfinite(raw). Otherwise execution uses its
                # alternative or continues below.
                if not math.isfinite(raw):
                    # Raise ValueError; normal execution of this block stops here.
                    raise ValueError
            # Enter this branch only when kind == 'boolean'. Otherwise execution uses its
            # alternative or continues below.
            elif kind == "boolean":
                # Enter this branch only when raw not in ('true', 'false'). Otherwise execution
                # uses its alternative or continues below.
                if raw not in ("true", "false"):
                    # Raise ValueError; normal execution of this block stops here.
                    raise ValueError
                # raw holds the source value before this step converts or normalizes it. Next,
                # evaluate raw == 'true'.
                raw = raw == "true"
            # Enter this branch only when kind == 'array'. Otherwise execution uses its
            # alternative or continues below.
            elif kind == "array":
                # raw holds the source value before this step converts or normalizes it. Next,
                # choose raw.split(',') when raw; otherwise use [].
                raw = raw.split(",") if raw else []
        # Handle (ValueError, TypeError) here. The original exception is not automatically safe to
        # expose to the client.
        except (ValueError, TypeError):
            # Stop this action with safe API error 'validation_error' (HTTP 400). The common
            # handler builds its JSON envelope.
            raise APIError(
                "validation_error", "Invalid parameter.", fields={name: ["Invalid value."]}
            ) from None
        # Set values[name]: reuse raw, which was prepared earlier in this function.
        values[name] = raw
    # Enter this branch only when path == '/api/v1/shared/{token}/'. Otherwise execution uses its
    # alternative or continues below.
    if path == "/api/v1/shared/{token}/":
        # Import re so the code below can use that module namespace.
        import re

        # Enter this branch only when not re.fullmatch('[A-Za-z0-9_-]{43,128}',
        # values.get('token', '')). Otherwise execution uses its alternative or continues below.
        if not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", values.get("token", "")):
            # Stop this action with safe API error 'not_found' (HTTP 404). The common handler
            # builds its JSON envelope.
            raise APIError("not_found", "Collection not found.", 404)
    # Call validate with the inputs shown; its definition explains the checks, side effects and
    # return value.
    validate(values, {"type": "object", "properties": properties, "required": required})
    # body holds the optional request-body schema for this endpoint. Next, look up a named
    # setting/value or make the indicated GET call; the surrounding object determines which.
    body = (
        operation.get("requestBody", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema")
    )
    # Validate against the documented request-body schema; bodyless endpoints reject extra JSON.
    # Enter this branch only when body. Otherwise execution uses its alternative or continues
    # below.
    if body:
        # serializer holds the DRF input checker, configured with this endpoint request-body
        # schema. Next, call ContractSerializer with the inputs shown; its definition explains the
        # checks, side effects and return value.
        serializer = ContractSerializer(data=request.data, schema=body)
        # Run the configured serializer rules; raise_exception=true stops the request on failure.
        serializer.is_valid(raise_exception=True)
        # data holds the cleaned submitted JSON body (or, in normalization helpers, the upstream
        # object being translated). Next, read serializer.validated_data from the indicated
        # object.
        data = serializer.validated_data
    else:
        # Enter this branch only when request.data. Otherwise execution uses its alternative or
        # continues below.
        if request.data:
            # Stop this action with safe API error 'validation_error' (HTTP 400). The common
            # handler builds its JSON envelope.
            raise APIError("validation_error", "Request body is not accepted.")
        # data holds the cleaned submitted JSON body (or, in normalization helpers, the upstream
        # object being translated). Next, build a dictionary with named fields.
        data = {}
    # Return the result to the caller: keep these related values together as a tuple: operation,
    # values, data.
    return operation, values, data
