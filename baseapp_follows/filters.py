import django_filters
import swapper

Follow = swapper.load_model("baseapp_follows", "Follow")


class FollowsFilter(django_filters.FilterSet):
    class Meta:
        model = Follow
        fields = ["target_is_following_back"]
