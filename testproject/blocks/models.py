from baseapp_blocks.models import AbstractBlock, AbstractBlockableMetadata


class Block(AbstractBlock):
    class Meta(AbstractBlock.Meta):
        pass


class BlockableMetadata(AbstractBlockableMetadata):
    class Meta(AbstractBlockableMetadata.Meta):
        pass
