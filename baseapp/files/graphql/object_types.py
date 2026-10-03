import django_filters
import graphene
import swapper

from baseapp_auth.graphql.permissions import PermissionsInterface
from baseapp_core.graphql import DjangoObjectType, FileInterface
from baseapp_core.graphql import Node as RelayNode
from baseapp_core.graphql import ThumbnailField
from baseapp_core.plugins import graphql_shared_interfaces

File = swapper.load_model("baseapp_files", "File")


class FileFilter(django_filters.FilterSet):
    no_parent = django_filters.BooleanFilter(field_name="parent", lookup_expr="isnull")

    class Meta:
        model = File
        fields = ["no_parent"]


class AbstractFileObjectType:
    parent = graphene.Field(RelayNode)
    thumbnail = ThumbnailField()

    class Meta:
        interfaces = graphql_shared_interfaces.get(
            RelayNode,
            PermissionsInterface,
            FileInterface,
            "CommentsInterface",
            "ReactionsInterface",
        )
        model = File
        filterset_class = FileFilter

    def resolve_url(self, info, **kwargs):
        if not self.file:
            if hasattr(self, "url"):
                return self.url
            return None
        return info.context.build_absolute_uri(self.file.url)

    def resolve_thumbnail(self, *args, **kwargs):
        return self.file


class FileObjectType(AbstractFileObjectType, DjangoObjectType):
    class Meta(AbstractFileObjectType.Meta):
        pass
