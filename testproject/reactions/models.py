from baseapp_reactions.models import AbstractReactableMetadata, AbstractReaction


class Reaction(AbstractReaction):
    class Meta(AbstractReaction.Meta):
        pass


class ReactableMetadata(AbstractReactableMetadata):
    class Meta(AbstractReactableMetadata.Meta):
        pass
