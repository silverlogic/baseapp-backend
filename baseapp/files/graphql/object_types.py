import django_filters
import graphene
import swapper

from baseapp_auth.graphql.permissions import PermissionsInterface
from baseapp_core.graphql import DjangoObjectType, FileInterface
from baseapp_core.graphql import Node as RelayNode
from baseapp_core.plugins import graphql_shared_interfaces

from .fields import FileThumbnailField

File = swapper.load_model("baseapp_files", "File")
file_app_label = File._meta.app_label
file_model_name = File._meta.model_name.lower()


def can_view_file(info: graphene.ResolveInfo, file_obj) -> bool:
    return info.context.user.has_perm(f"{file_app_label}.view_{file_model_name}", file_obj)


class FileFilter(django_filters.FilterSet):
    no_parent = django_filters.BooleanFilter(field_name="parent", lookup_expr="isnull")

    class Meta:
        model = File
        fields = ["no_parent"]


class AbstractFileObjectType:
    parent = graphene.Field(RelayNode)
    thumbnail = FileThumbnailField()

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

    @classmethod
    def get_node(cls, info: graphene.ResolveInfo, id: str):
        node = super().get_node(info, id)
        if node is not None and not can_view_file(info, node):
            return None
        return node

    def resolve_url(self, info, **kwargs):
        """On private storage the URL is signed and expires; None for viewers
        without ``view_file``."""
        if not can_view_file(info, self):
            return None
        if not self.file:
            if hasattr(self, "url"):
                return self.url
            return None
        return info.context.build_absolute_uri(self.file.url)

    def resolve_thumbnail(self, info, **kwargs):
        """Same rule as ``url``: None for viewers without ``view_file``."""
        if not can_view_file(info, self):
            return None
        return self.file


class FileObjectType(AbstractFileObjectType, DjangoObjectType):
    class Meta(AbstractFileObjectType.Meta):
        pass
