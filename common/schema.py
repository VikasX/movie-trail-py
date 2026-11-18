# FILE PURPOSE: Gives drf-spectacular the reviewed OpenAPI document used by Swagger.
# Import copy so the code below can use that module namespace.
import copy

# Import SchemaGenerator from drf_spectacular.generators (the named Python helper module).
from drf_spectacular.generators import SchemaGenerator

# Import specification from common.contract (our shared API layer).
from common.contract import specification


class ContractSchemaGenerator(SchemaGenerator):
    # Return a copy of the reviewed contract so documentation generation cannot mutate the
    # shared definition.
    def get_schema(self, request=None, public=False):
        # INPUTS TO THIS FUNCTION: self = this class instance; request = current browser/user
        # context; public = argument supplied by the caller.
        # Return the result to the caller: call copy.deepcopy with the inputs shown; its
        # definition explains the checks, side effects and return value.
        return copy.deepcopy(specification())
