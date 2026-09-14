from baseapp_follows.models import AbstractFollow, AbstractFollowableMetadata


class Follow(AbstractFollow):
    class Meta(AbstractFollow.Meta):
        pass


class FollowableMetadata(AbstractFollowableMetadata):
    class Meta(AbstractFollowableMetadata.Meta):
        pass
