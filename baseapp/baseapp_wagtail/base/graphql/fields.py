from graphene.types import Scalar
from graphene_django.converter import convert_django_field
from wagtail.fields import StreamField
from wagtail.blocks import StreamValue


class GenericStreamFieldType(Scalar):
    @staticmethod
    def serialize(stream_value):
        return stream_value.stream_block.get_api_representation(stream_value) if isinstance(stream_value, StreamValue) else []


# @convert_django_field.register(StreamField)
# def convert_stream_field(field, registry=None):
#     return GenericStreamFieldType(
#         description=field.help_text, required=not field.null
#     )
