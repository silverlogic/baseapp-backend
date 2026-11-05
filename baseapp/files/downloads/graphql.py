from typing import Any, Optional

import graphene
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from graphql.error import GraphQLError
from graphql_relay import from_global_id
from rest_framework.exceptions import APIException

from baseapp_core.graphql import RelayMutation
from baseapp_core.hashids.utils import is_uuid4

from .registry import ProtectedFileSpec, protected_files
from .services import (
    ProtectedFileInfo,
    describe_protected_file,
    get_protected_object,
    link_expires_at,
    ticket_path,
)
from .tickets import ProtectedDownloadTicket


class ProtectedFile(graphene.ObjectType):
    """A file served only through permission-checked downloads; mint a link with ``protectedFileLink``."""

    key = graphene.String(required=True, description=_("Registry key of the file field."))
    object_id = graphene.ID(required=True, description=_("Id of the object holding the file."))
    file_name = graphene.String(description=_("Name the file downloads as."))
    content_type = graphene.String(description=_("Type the file is served with."))
    size = graphene.BigInt(description=_("Size in bytes; null when unknown."))

    class Meta:
        name = "ProtectedFile"


class ProtectedFileField(graphene.Field):
    """
    A ``ProtectedFile`` for a registered file field of the object being resolved; null when
    the field is empty or the viewer may not download it.

        class InvoiceObjectType(DjangoObjectType):
            pdf = ProtectedFileField("pdf")
    """

    def __init__(self, field_name: str, *, key: Optional[str] = None, **kwargs: Any) -> None:
        self.protected_field_name = field_name
        self.protected_key = key
        kwargs.setdefault("description", _("The protected file, or null without access."))
        super().__init__(ProtectedFile, resolver=self.resolve_protected_file, **kwargs)

    def get_spec(self, root: Any) -> Optional[ProtectedFileSpec]:
        if self.protected_key:
            return protected_files.get(self.protected_key)
        return protected_files.get_for(root, self.protected_field_name)

    def resolve_protected_file(
        self, root: Any, info: graphene.ResolveInfo, **kwargs: Any
    ) -> Optional[ProtectedFileInfo]:
        return describe_protected_file(self.get_spec(root), root, info.context.user)


def graphql_error(exc: Exception) -> GraphQLError:
    """A client-safe GraphQLError for an access failure, keeping its code."""
    if isinstance(exc, APIException):
        codes = exc.get_codes()
        code = codes if isinstance(codes, str) else exc.default_code
        detail = exc.detail if isinstance(exc.detail, str) else exc.default_detail
        return GraphQLError(str(detail), extensions={"code": code})
    if isinstance(exc, Http404):
        return GraphQLError(str(_("File not found.")), extensions={"code": "not_found"})
    return GraphQLError(
        str(_("You don't have permission to download this file.")),
        extensions={"code": "permission_denied"},
    )


def resolve_lookup_value(
    info: graphene.ResolveInfo, spec: ProtectedFileSpec, object_id: str
) -> Any:
    """
    ``objectId`` is the spec's lookup value; a Relay global id of the model (legacy
    ``base64("Type:pk")`` or a public id) is accepted too.
    """
    if (
        is_uuid4(object_id)
        and not spec.uses_public_id()
        and hasattr(spec.model, "get_by_public_id")
    ):
        try:
            obj = spec.model.get_by_public_id(object_id)
        except (ObjectDoesNotExist, ValueError, ValidationError):
            obj = None
        return getattr(obj, spec.lookup_field) if isinstance(obj, spec.model) else object_id

    type_name, pk = from_global_id(object_id)  # ("", ...) when it is not a global id
    object_type = info.schema.get_type(type_name) if type_name else None
    model = getattr(
        getattr(getattr(object_type, "graphene_type", None), "_meta", None), "model", None
    )
    if not (pk and isinstance(model, type) and issubclass(model, spec.model)):
        return object_id
    if spec.lookup_field == "pk":
        return pk
    try:
        obj = spec.model._default_manager.filter(pk=pk).first()
    except (ValueError, ValidationError):
        obj = None
    return getattr(obj, spec.lookup_field) if obj is not None else object_id


class ProtectedFileLink(RelayMutation):
    """
    Mint a short-lived download link for a protected file, bound to the caller (and the
    profile they act as). Opening it re-checks access, so it opens natively in the browser
    without headers.

        mutation {
            protectedFileLink(input: {key: "billing.invoice.pdf", objectId: "42"}) {
                url
                expiresAt
            }
        }
    """

    url = graphene.String(description=_("Absolute download URL."))
    expires_at = graphene.DateTime(description=_("When the link stops working."))
    file = graphene.Field(ProtectedFile)

    class Input:
        key = graphene.String(required=True, description=_("ProtectedFile.key"))
        object_id = graphene.ID(
            required=True, description=_("ProtectedFile.objectId, or the object's Relay id.")
        )

    @classmethod
    def mutate_and_get_payload(
        cls, root: Any, info: graphene.ResolveInfo, key: str, object_id: str, **input: Any
    ) -> "ProtectedFileLink":
        spec = protected_files.get(key)
        if spec is None:
            raise GraphQLError(str(_("File not found.")), extensions={"code": "not_found"})

        user = info.context.user
        try:
            obj = get_protected_object(spec, user, resolve_lookup_value(info, spec, object_id))
        except (APIException, Http404, DjangoPermissionDenied) as exc:
            raise graphql_error(exc) from None
        if spec.is_empty(obj):
            raise GraphQLError(str(_("File not found.")), extensions={"code": "not_found"})

        ticket = ProtectedDownloadTicket.mint(spec, obj, user)
        return ProtectedFileLink(
            url=info.context.build_absolute_uri(ticket_path(ticket)),
            expires_at=link_expires_at(ProtectedDownloadTicket.max_age()),
            file=ProtectedFileInfo(spec, obj),
        )


class ProtectedFileMutations:
    protected_file_link = ProtectedFileLink.Field()
