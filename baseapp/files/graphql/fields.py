from collections.abc import Callable

import graphene

from baseapp_core.graphql import ThumbnailField

from ..storage import files_storage, files_storage_is_private
from ..thumbnails import private_thumbnail_name


class FileThumbnailField(ThumbnailField):
    """
    ``ThumbnailField`` that keeps a private file's thumbnail private.

    Public storage keeps the shared behaviour (public thumbnail storage, cached URL). On
    private storage the thumbnail is generated into the files storage itself and returned
    as a freshly signed URL, like ``url``; the resolver decides who may see it.
    """

    def get_resolver(self, parent_resolver) -> Callable:
        public_resolver = super().get_resolver(parent_resolver)
        resolver = self.resolver or parent_resolver

        def resolve(instance, info: graphene.ResolveInfo, width: int, height: int, **kwargs):
            if not files_storage_is_private():
                return public_resolver(instance, info, width, height, **kwargs)

            field_file = resolver(instance, info, **kwargs)
            if not field_file:
                return None
            name = private_thumbnail_name(field_file, width, height)
            if not name:
                return None
            return info.context.build_absolute_uri(files_storage.url(name))

        return resolve
