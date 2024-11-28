from django.utils.translation import gettext_lazy as _
from wagtail.images.formats import (
    Format,
    register_image_format,
    unregister_image_format,
)

unregister_image_format(
    Format("fullwidth", _("Full width"), "richtext-image full-width", "width-800")
)
register_image_format(
    Format("fullwidth", _("Full width"), "richtext-image full-width", "width-1472")
)
register_image_format(
    Format("originalsize", _("Original size"), "richtext-image original-size", "original")
)
register_image_format(
    Format(
        "centered",
        _("Centered"),
        "richtext-image centered",
        "width-300",
    )
)
