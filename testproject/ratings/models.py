from baseapp_ratings.models import AbstractRatableMetadata, AbstractRate


class Rate(AbstractRate):
    class Meta(AbstractRate.Meta):
        pass


class RatableMetadata(AbstractRatableMetadata):
    class Meta(AbstractRatableMetadata.Meta):
        pass
