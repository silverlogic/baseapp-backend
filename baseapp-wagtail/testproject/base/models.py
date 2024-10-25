from baseapp_wagtail.base.models import BaseStandardPage
from baseapp_wagtail.base.stream_fields import PageBodyStreamField

from .stream_fields.standard_page_stream_block import StandardPageStreamBlock


class StandardPage(BaseStandardPage):
    body = PageBodyStreamField.create(
        StandardPageStreamBlock(required=False),
    )
