import swapper
from rest_framework import serializers

from baseapp_core.graphql import get_obj_relay_id
from baseapp_core.rest_framework.fields import ThumbnailImageField

Profile = swapper.load_model("baseapp_profiles", "Profile")


class JWTProfileSerializer(serializers.ModelSerializer):
    """
    Serialize minimal profile data for token and auth-related payloads.
    """

    id = serializers.SerializerMethodField()
    url_path = serializers.SerializerMethodField()
    image = ThumbnailImageField(required=False, sizes={"small": (100, 100)})

    class Meta:
        model = Profile
        fields = ("id", "name", "image", "url_path")

    def get_id(self, profile) -> str:
        return get_obj_relay_id(profile)

    def get_url_path(self, profile) -> str | None:
        path_obj = getattr(profile, "url_path", None)
        return getattr(path_obj, "path", None)

    def to_representation(self, profile) -> dict:
        data = super().to_representation(profile)
        if data["image"] is not None:
            data["image"] = data["image"]["small"]
        return data
