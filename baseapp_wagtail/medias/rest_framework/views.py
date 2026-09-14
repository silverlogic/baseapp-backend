from rest_framework.permissions import AllowAny
from wagtail.images.api.v2.views import ImagesAPIViewSet


class CustomImagesAPIViewSet(ImagesAPIViewSet):
    # Wagtail's BaseAPIViewSet sets no permission_classes, so it inherits
    # REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"]. These endpoints serve public pages;
    # pin them so a future tightening of that default cannot 401 the public site.
    permission_classes = (AllowAny,)
