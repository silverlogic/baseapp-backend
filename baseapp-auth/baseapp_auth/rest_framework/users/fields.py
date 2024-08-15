from baseapp_core.rest_framework.fields import ThumbnailImageField


class AvatarField(ThumbnailImageField):
    def __init__(self, *args, **kwargs):
        if "sizes" not in kwargs:
            kwargs["sizes"] = {"small": (64, 64), "full_size": (1024, 1024)}
        super().__init__(*args, **kwargs)
