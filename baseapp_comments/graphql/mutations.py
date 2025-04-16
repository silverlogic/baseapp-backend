import graphene
import swapper
from django import forms
from django.apps import apps
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from graphene_django.forms.mutation import _set_errors_flag_to_context
from graphene_django.types import ErrorType
from graphql.error import GraphQLError

from baseapp_core.graphql import (
    RelayMutation,
    get_obj_from_relay_id,
    get_pk_from_relay_id,
    login_required,
)

from .object_types import CommentsInterface

Comment = swapper.load_model("baseapp_comments", "Comment")
app_label = Comment._meta.app_label
CommentObjectType = Comment.get_graphql_object_type()


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ("body",)


class CommentCreate(RelayMutation):
    comment = graphene.Field(CommentObjectType._meta.connection.Edge)

    class Input:
        target_object_id = graphene.ID(required=True)
        in_reply_to_id = graphene.ID(required=False)
        profile_id = graphene.ID(required=False)
        body = graphene.String(required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        activity_name = f"{app_label}.add_comment"

        if apps.is_installed("baseapp.activity_log"):
            from baseapp.activity_log.context import set_public_activity

            set_public_activity(verb=activity_name)

        target = get_obj_from_relay_id(info, input.get("target_object_id"))

        if not info.context.user.has_perm(activity_name, target):
            raise GraphQLError(
                str(_("You don't have permission to perform this action")),
                extensions={"code": "permission_required"},
            )

        comment = Comment(user=info.context.user, target=target, body=input.get("body"))

        if input.get("profile_id") or info.context.user.current_profile:
            comment.profile = (
                get_obj_from_relay_id(info, input.get("profile_id"))
                if input.get("profile_id")
                else info.context.user.current_profile
            )

            if not info.context.user.has_perm(
                f"{app_label}.add_comment_with_profile", comment.profile
            ):
                raise GraphQLError(
                    str(_("You don't have permission to perform this action")),
                    extensions={"code": "permission_required"},
                )

        if input.get("in_reply_to_id"):
            comment.in_reply_to = get_obj_from_relay_id(info, input.get("in_reply_to_id"))

            if not info.context.user.has_perm(f"{app_label}.reply_comment", comment.in_reply_to):
                raise GraphQLError(
                    str(_("You don't have permission to perform this action")),
                    extensions={"code": "permission_required"},
                )

        form = CommentForm(instance=comment, data=input)
        if form.is_valid():
            form.save()

            # Need to refresh to update comments_count
            target.refresh_from_db()
            if comment.profile:
                comment.profile.refresh_from_db()
            if comment.in_reply_to:
                comment.in_reply_to.refresh_from_db()

            return cls(
                comment=CommentObjectType._meta.connection.Edge(node=comment),
            )
        else:
            errors = ErrorType.from_errors(form.errors)
            _set_errors_flag_to_context(info)

            return cls(errors=errors)


class CommentUpdate(RelayMutation):
    comment = graphene.Field(CommentObjectType)

    class Input:
        id = graphene.ID(required=True)
        body = graphene.String(required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        pk = get_pk_from_relay_id(input.get("id"))
        comment = Comment.objects.get(pk=pk)
        activity_name = f"{app_label}.change_comment"

        if not info.context.user.has_perm(activity_name, comment):
            raise GraphQLError(
                str(_("You don't have permission to perform this action")),
                extensions={"code": "permission_required"},
            )

        if apps.is_installed("baseapp.activity_log"):
            from baseapp.activity_log.context import set_public_activity

            set_public_activity(verb=activity_name)

        comment.is_edited = True

        form = CommentForm(instance=comment, data=input)
        if form.is_valid():
            comment = form.save()
            return cls(
                comment=comment,
            )
        else:
            errors = ErrorType.from_errors(form.errors)
            _set_errors_flag_to_context(info)

            return cls(errors=errors)


class CommentPin(RelayMutation):
    comment = graphene.Field(CommentObjectType)

    class Input:
        id = graphene.ID(required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        pk = get_pk_from_relay_id(input.get("id"))
        comment = Comment.objects.get(pk=pk)
        activity_name = f"{app_label}.pin_comment"

        if not info.context.user.has_perm(activity_name, comment):
            raise GraphQLError(
                str(_("You don't have permission to perform this action")),
                extensions={"code": "permission_required"},
            )

        if apps.is_installed("baseapp.activity_log"):
            from baseapp.activity_log.context import set_public_activity

            set_public_activity(verb=activity_name)

        MAX_PINS_PER_THREAD = getattr(settings, "BASEAPP_COMMENTS_MAX_PINS_PER_THREAD", None)
        if MAX_PINS_PER_THREAD is not None:
            if comment.in_reply_to_id:
                qs = Comment.objects_visible.filter(in_reply_to_id=comment.in_reply_to_id)
            else:
                qs = Comment.objects_visible.filter(
                    target_object_id=comment.target_object_id,
                    target_content_type_id=comment.target_content_type_id,
                    in_reply_to__isnull=True,
                )

            if qs.filter(is_pinned=True).count() >= MAX_PINS_PER_THREAD:
                raise GraphQLError(
                    str(
                        _("You can't pin more than %(max_pins)s comments in this thread")
                        % {"max_pins": MAX_PINS_PER_THREAD}
                    ),
                    extensions={"code": "max_pins_reached"},
                )

        comment.is_pinned = not comment.is_pinned
        comment.save()

        return CommentPin(comment=comment)


class CommentDelete(RelayMutation):
    deleted_id = graphene.ID()
    target = graphene.Field(CommentsInterface)
    in_reply_to = graphene.Field(CommentObjectType)

    class Input:
        id = graphene.ID(required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        relay_id = input.get("id")
        pk = get_pk_from_relay_id(relay_id)
        obj = Comment.objects.get(pk=pk)

        error_exception = GraphQLError(
            str(_("You don't have permission to perform this action")),
            extensions={"code": "permission_required"},
        )
        if not obj:
            raise error_exception

        if not info.context.user.has_perm(f"{app_label}.delete_comment", obj):
            raise error_exception

        target = obj.target
        in_reply_to = obj.in_reply_to

        obj.delete()

        return CommentDelete(deleted_id=relay_id, target=target, in_reply_to=in_reply_to)


class CommentsMutations(object):
    comment_create = CommentCreate.Field()
    comment_update = CommentUpdate.Field()
    comment_pin = CommentPin.Field()
    comment_delete = CommentDelete.Field()
