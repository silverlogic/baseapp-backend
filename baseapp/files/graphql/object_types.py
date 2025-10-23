import django_filters
import graphene
import swapper
from graphene import relay

from baseapp_core.graphql import DjangoObjectType

File = swapper.load_model("baseapp_files", "File")


class FileFilter(django_filters.FilterSet):
    no_parent = django_filters.BooleanFilter(field_name="parent_object_id", lookup_expr="isnull")

    class Meta:
        model = File
        fields = ["no_parent"]


class FileObjectType(DjangoObjectType):
    parent = graphene.Field(relay.Node)
    url = graphene.String()

    class Meta:
        interfaces = (relay.Node,)
        model = File
        filterset_class = FileFilter

    def resolve_url(self, info, **kwargs):
        if not self.file:
            return None
        return info.context.build_absolute_uri(self.file.url)

    # @classmethod
    # def get_node(cls, info, id):
    #     if not info.context.user.is_authenticated:
    #         return None

    #     try:
    #         queryset = cls.get_queryset(cls._meta.model.objects, info)
    #         return queryset.get(id=id, recipient=info.context.user)
    #     except cls._meta.model.DoesNotExist:
    #         return None
