import swapper
from django.utils.translation import gettext_lazy as _
from graphql.error import GraphQLError

from baseapp_core.graphql import get_pk_from_relay_id

from ..utils import set_files_parent


def attach_files_from_relay_ids(parent, file_ids, user):
    if file_ids in (None, []):
        return

    File = swapper.load_model("baseapp_files", "File")
    file_pks = [get_pk_from_relay_id(file_id) for file_id in file_ids]
    pk_lookup = [str(pk) for pk in file_pks]
    files_qs = File.objects.filter(pk__in=file_pks)
    files_map = {str(file.pk): file for file in files_qs}

    missing = [pk for pk in pk_lookup if pk not in files_map]
    if missing:
        raise GraphQLError(
            str(_("One or more files could not be found")),
            extensions={"code": "not_found"},
        )

    files = [files_map[pk] for pk in pk_lookup]

    if user and not user.is_superuser:
        unauthorized = [
            file_obj
            for file_obj in files
            if file_obj.created_by_id and file_obj.created_by_id != user.id
        ]
        if unauthorized:
            raise GraphQLError(
                str(_("You don't have permission to perform this action")),
                extensions={"code": "permission_required"},
            )

    set_files_parent(parent, files)
