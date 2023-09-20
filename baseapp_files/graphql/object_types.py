import django_filters
import graphene
from graphene import relay
from graphene.types.generic import GenericScalar
from baseapp_core.graphql import DjangoObjectType
from graphene_django.filter import DjangoFilterConnectionField
from django.contrib.contenttypes.models import ContentType

from ..models import File


class FileFilter(django_filters.FilterSet):
    no_parent = django_filters.BooleanFilter(field_name='parent_object_id', lookup_expr='isnull')

    class Meta:
        model = File
        fields = ['no_parent']


class FileObjectType(DjangoObjectType):
    parent = graphene.Field(relay.Node)
    url = graphene.String()

    class Meta:
        interfaces = (relay.Node,)
        model = File
        filterset_class = FileFilter
    
    def resolve_url(self, info, **kwargs):
        # return self.file.url
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


class FilesNode(relay.Node):
    files_count = GenericScalar()
    files = DjangoFilterConnectionField(lambda: FileObjectType)

    def resolve_files(self, info, **kwargs):
        parent_content_type = ContentType.objects.get_for_model(self)
        return File.objects.filter(
            parent_content_type=parent_content_type,
            parent_object_id=self.pk,
        ).order_by("-created")
