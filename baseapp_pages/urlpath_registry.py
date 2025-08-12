from typing import Dict, List, Type

from django.contrib.contenttypes.models import ContentType
from django.db.models import Model


class URLPathRegistry:
    def __init__(self):
        self._graphql_types: Dict[str, Type] = {}

    def register_type(self, model_class: Type[Model], graphql_type: Type):
        content_type = ContentType.objects.get_for_model(model_class)
        key = f"{content_type.app_label}.{content_type.model}"
        self._graphql_types[key] = graphql_type

    def get_type(self, instance: Model) -> Type:
        content_type = ContentType.objects.get_for_model(instance)
        key = f"{content_type.app_label}.{content_type.model}"
        return self._graphql_types.get(key)

    def get_all_types(self) -> List[Type]:
        return list(set(self._graphql_types.values()))


# Global registry instance
urlpath_registry = URLPathRegistry()


def register_urlpath_type(model_class: Type[Model], graphql_type: Type):
    """Decorator to register a GraphQL type for a model"""
    urlpath_registry.register_type(model_class, graphql_type)
    return model_class
