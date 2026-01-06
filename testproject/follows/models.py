from baseapp_follows.models import AbstractBaseFollow


class Follow(AbstractBaseFollow):

    class Meta(AbstractBaseFollow.Meta):
        unique_together = [("actor", "target")]
