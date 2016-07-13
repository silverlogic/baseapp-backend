from avatar.templatetags.avatar_tags import avatar_url

from apps.api.fields import ThumbnailImageField


class AvatarField(ThumbnailImageField):
    def get_attribute(self, obj):
        return obj

    def to_representation(self, instance):
        user = instance
        return {
            'full_size': avatar_url(user, 1024),
            'small': avatar_url(user, 64),
        }
