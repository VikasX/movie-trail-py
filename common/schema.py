import copy

from drf_spectacular.generators import SchemaGenerator

from common.contract import specification


class ContractSchemaGenerator(SchemaGenerator):
    def get_schema(self, request=None, public=False):
        return copy.deepcopy(specification())
