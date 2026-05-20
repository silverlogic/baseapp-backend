from baseapp_blocks.base import AbstractBlock
from baseapp_blocks.models import AbstractBlockableMetadata


class Block(AbstractBlock):
    class Meta(AbstractBlock.Meta):
        pass


class BlockableMetadata(AbstractBlockableMetadata):
    class Meta(AbstractBlockableMetadata.Meta):
        pass
