from baseapp_ratings.models import AbstractBaseRate


class Rate(AbstractBaseRate):
    class Meta(AbstractBaseRate.Meta):
        unique_together = [["user", "target_content_type", "target_object_id"]]
        db_table = "baseapp_ratings_rate"

    @classmethod
    def get_graphql_object_type(cls):
        from baseapp_ratings.graphql.object_types import RatingObjectType

        return RatingObjectType
