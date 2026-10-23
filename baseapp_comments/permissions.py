from typing import TYPE_CHECKING

import swapper
from django.apps import apps
from django.contrib.auth.backends import BaseBackend

from .models import CommentStatus

if TYPE_CHECKING:
    from django.contrib.auth.base_user import AbstractBaseUser
    from django.contrib.auth.models import AnonymousUser
    from django.db.models import Model

Comment = swapper.load_model("baseapp_comments", "Comment")
app_label = Comment._meta.app_label


def _is_comments_enabled(obj) -> bool:
    from baseapp_core.plugins import shared_services

    if service := shared_services.get("commentable_metadata"):
        return service.is_comments_enabled(obj)
    return False


class CommentsPermissionsBackend(BaseBackend):
    def has_perm(self, user_obj, perm, obj=None) -> bool | None:
        if perm in [f"{app_label}.add_comment", f"{app_label}.reply_comment"]:
            return self._can_add_comment(user_obj, obj)

        if perm == f"{app_label}.view_target_comments":
            # Read gate for the comments of a target (obj): its comments, its comments count,
            # node(id) of each comment and the comment subscription. Granted by default, so the
            # comments list and the subscription keep applying
            # BASEAPP_COMMENTS_CAN_ANONYMOUS_VIEW_COMMENTS on their own as before. Subclass this
            # backend to restrict a target. When a comment is the target, obj is that comment.
            return True

        if perm == f"{app_label}.publish_comment_activity":
            # Whether creating, editing or pinning a comment on the target (obj) is logged as a
            # public activity in baseapp.activity_log. Deny it where comments are private.
            return True

        if perm == f"{app_label}.view_comment":
            if not obj:
                # Anyone can view a comment
                return True
            elif isinstance(obj, Comment):
                if obj.target_document_id and not user_obj.has_perm(
                    f"{app_label}.view_target_comments", obj.target
                ):
                    return False

                if obj.status == CommentStatus.PUBLISHED:
                    return True

                # Only users who has change permission can view unpublished comments
                return user_obj.has_perm(f"{app_label}.change_comment", obj)

        if perm in [f"{app_label}.change_comment", f"{app_label}.delete_comment"]:
            if isinstance(obj, Comment):
                if obj.target and not _is_comments_enabled(obj.target):
                    return False

                if user_obj.is_authenticated:
                    # Owner can change or delete their own comments
                    if obj.user_id == user_obj.id:
                        return True

                    # Anyone with permission can change and delete any comment
                    return user_obj.has_perm(perm)

        if perm == f"{app_label}.pin_comment" and obj is not None:
            # Anyone with permission can pin any comment
            return user_obj.has_perm(perm)

        if apps.is_installed("baseapp_profiles"):
            Profile = swapper.load_model("baseapp_profiles", "Profile")
            profile_app_label = Profile._meta.app_label
            if perm == f"{app_label}.add_comment_with_profile" and obj:
                return user_obj.has_perm(f"{profile_app_label}.use_profile", obj)

    def _can_add_comment(
        self, user_obj: "AbstractBaseUser | AnonymousUser", obj: "Model | None"
    ) -> bool:
        """`add_comment` / `reply_comment` on `obj`, the target or the comment replied to."""
        if not (user_obj.is_authenticated and _is_comments_enabled(obj)):
            return False
        # Commenting on or replying to a comment returns it in the mutation payload
        # (`inReplyTo`, `target`), so it must be one the user can see.
        if isinstance(obj, Comment):
            return user_obj.has_perm(f"{app_label}.view_comment", obj)
        return True
