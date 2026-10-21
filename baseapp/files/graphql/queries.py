import graphene
import swapper
from django.db import models
from graphene_django.filter import DjangoFilterConnectionField

from baseapp_core.graphql import Node

File = swapper.load_model("baseapp_files", "File")
FileObjectType = File.get_graphql_object_type()


class FilesQueries:
    my_files = DjangoFilterConnectionField(
        FileObjectType, description="Files created by the current user."
    )
    file = Node.Field(FileObjectType)

    def resolve_my_files(self, info: graphene.ResolveInfo, **kwargs) -> models.QuerySet:
        if not info.context.user.is_authenticated:
            return File.objects.none()
        # Explicit total ordering — AbstractFile has no Meta.ordering, and cursor
        # pagination over an unordered queryset yields duplicated/missing rows.
        return File.objects.filter(created_by=info.context.user).order_by("-created", "-pk")
