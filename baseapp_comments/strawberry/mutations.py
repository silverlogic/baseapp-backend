import strawberry
import swapper
from django import forms
from django.apps import apps
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from graphql.error import GraphQLError
from strawberry import UNSET
from strawberry.types import Info

from baseapp_core.graphql import get_obj_from_relay_id, get_pk_from_relay_id
from baseapp_core.plugins import shared_services
from baseapp_core.strawberry import (
    ErrorType,
    RelayMutationInput,
    RelayMutationPayload,
    relay_mutation,
)
from baseapp_core.strawberry.connections import Edge

from .interfaces import CommentsInterface
from .types import CommentLazyType

Comment = swapper.load_model("baseapp_comments", "Comment")
app_label = Comment._meta.app_label


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ("body",)


def _permission_error() -> GraphQLError:
    return GraphQLError(
        str(_("You don't have permission to perform this action")),
        extensions={"code": "permission_required"},
    )


def _form_errors(form: forms.Form) -> list[ErrorType]:
    return [ErrorType(field=key, messages=list(value)) for key, value in form.errors.items()]


@strawberry.input(name="CommentCreateInput")
class CommentCreateInput(RelayMutationInput):
    target_object_id: strawberry.ID
    in_reply_to_id: strawberry.ID | None = UNSET
    body: str
    mentioned_profile_ids: list[strawberry.ID | None] | None = UNSET
    if apps.is_installed("baseapp_profiles"):
        profile_id: strawberry.ID | None = UNSET


@strawberry.type(name="CommentCreatePayload")
class CommentCreatePayload(RelayMutationPayload):
    comment: Edge[CommentLazyType] | None = None


@strawberry.input(name="CommentUpdateInput")
class CommentUpdateInput(RelayMutationInput):
    id: strawberry.ID
    body: str
    mentioned_profile_ids: list[strawberry.ID | None] | None = UNSET


@strawberry.type(name="CommentUpdatePayload")
class CommentUpdatePayload(RelayMutationPayload):
    comment: CommentLazyType | None = None


@strawberry.input(name="CommentPinInput")
class CommentPinInput(RelayMutationInput):
    id: strawberry.ID


@strawberry.type(name="CommentPinPayload")
class CommentPinPayload(RelayMutationPayload):
    comment: CommentLazyType | None = None


@strawberry.input(name="CommentDeleteInput")
class CommentDeleteInput(RelayMutationInput):
    id: strawberry.ID


@strawberry.type(name="CommentDeletePayload")
class CommentDeletePayload(RelayMutationPayload):
    deleted_id: strawberry.ID | None = None
    target: CommentsInterface | None = None
    in_reply_to: CommentLazyType | None = None


def _update_mentions(info: Info, comment: Comment, mentioned_profile_ids: list) -> None:
    if service := shared_services.get("mentions"):
        service.update_mentions(
            comment,
            mentioned_profile_ids,
            exclude_profile=getattr(info.context.user, "current_profile", None),
        )


@strawberry.type
class CommentsMutations:
    @relay_mutation(login_required=True)
    def comment_create(self, info: Info, input: CommentCreateInput) -> CommentCreatePayload | None:
        user = info.context.user
        activity_name = f"{app_label}.add_comment"

        if service := shared_services.get("activity_log"):
            service.set_public_activity(verb=activity_name)

        target = get_obj_from_relay_id(info, input.target_object_id)

        if not user.has_perm(activity_name, target):
            raise _permission_error()

        comment = Comment(user=user, target=target, body=input.body)

        if apps.is_installed("baseapp_profiles"):
            profile_id = input.profile_id
            if profile_id or user.current_profile:
                comment.profile = (
                    get_obj_from_relay_id(info, profile_id) if profile_id else user.current_profile
                )

                if not user.has_perm(f"{app_label}.add_comment_with_profile", comment.profile):
                    raise _permission_error()

        if input.in_reply_to_id:
            comment.in_reply_to = get_obj_from_relay_id(info, input.in_reply_to_id)

            if not user.has_perm(f"{app_label}.reply_comment", comment.in_reply_to):
                raise _permission_error()

        mentioned_profile_ids = input.mentioned_profile_ids or []
        form = CommentForm(instance=comment, data={"body": input.body})
        if not form.is_valid():
            return CommentCreatePayload(errors=_form_errors(form))

        form.save()

        if hasattr(comment, "profile") and comment.profile:
            comment.profile.refresh_from_db()
        if comment.in_reply_to:
            comment.in_reply_to.refresh_from_db()

        if mentioned_profile_ids:
            _update_mentions(info, comment, mentioned_profile_ids)

        return CommentCreatePayload(comment=Edge(node=comment, cursor=None))

    @relay_mutation(login_required=True)
    def comment_update(self, info: Info, input: CommentUpdateInput) -> CommentUpdatePayload | None:
        user = info.context.user
        mentioned_profile_ids = (
            None if input.mentioned_profile_ids is UNSET else input.mentioned_profile_ids
        )
        comment = Comment.objects.get(pk=get_pk_from_relay_id(input.id))
        activity_name = f"{app_label}.change_comment"

        if not user.has_perm(activity_name, comment):
            raise _permission_error()

        if service := shared_services.get("activity_log"):
            service.set_public_activity(verb=activity_name)

        comment.is_edited = True

        form = CommentForm(instance=comment, data={"body": input.body})
        if not form.is_valid():
            return CommentUpdatePayload(errors=_form_errors(form))

        comment = form.save()

        if mentioned_profile_ids is not None:
            _update_mentions(info, comment, mentioned_profile_ids)

        return CommentUpdatePayload(comment=comment)

    @relay_mutation(login_required=True)
    def comment_pin(self, info: Info, input: CommentPinInput) -> CommentPinPayload | None:
        comment = Comment.objects.get(pk=get_pk_from_relay_id(input.id))
        activity_name = f"{app_label}.pin_comment"

        if not info.context.user.has_perm(activity_name, comment):
            raise _permission_error()

        if service := shared_services.get("activity_log"):
            service.set_public_activity(verb=activity_name)

        max_pins = getattr(settings, "BASEAPP_COMMENTS_MAX_PINS_PER_THREAD", None)
        if max_pins is not None:
            if comment.in_reply_to_id:
                qs = Comment.objects_visible.filter(in_reply_to_id=comment.in_reply_to_id)
            else:
                qs = Comment.objects_visible.filter(
                    target_document_id=comment.target_document_id,
                    in_reply_to__isnull=True,
                )

            if qs.filter(is_pinned=True).count() >= max_pins:
                raise GraphQLError(
                    str(
                        _("You can't pin more than %(max_pins)s comments in this thread")
                        % {"max_pins": max_pins}
                    ),
                    extensions={"code": "max_pins_reached"},
                )

        comment.is_pinned = not comment.is_pinned
        comment.save()

        return CommentPinPayload(comment=comment)

    @relay_mutation(login_required=True)
    def comment_delete(self, info: Info, input: CommentDeleteInput) -> CommentDeletePayload | None:
        relay_id = input.id
        obj = Comment.objects.get(pk=get_pk_from_relay_id(relay_id))

        if not info.context.user.has_perm(f"{app_label}.delete_comment", obj):
            raise _permission_error()

        target = obj.target
        in_reply_to = obj.in_reply_to

        obj.delete()

        return CommentDeletePayload(deleted_id=relay_id, target=target, in_reply_to=in_reply_to)
