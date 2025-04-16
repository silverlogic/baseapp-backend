import swapper
from django.contrib.auth.backends import BaseBackend

from .models import CommentStatus

Comment = swapper.load_model("baseapp_comments", "Comment")
app_label = Comment._meta.app_label
Profile = swapper.load_model("baseapp_profiles", "Profile")
profile_app_label = Profile._meta.app_label


class CommentsPermissionsBackend(BaseBackend):
    def has_perm(self, user_obj, perm, obj=None):
        if perm in [f"{app_label}.add_comment", f"{app_label}.reply_comment"]:
            return user_obj.is_authenticated and getattr(obj, "is_comments_enabled", False)

        if perm == f"{app_label}.view_comment":
            if not obj:
                # Anyone can view a comment
                return True
            elif isinstance(obj, Comment):
                if obj.status == CommentStatus.PUBLISHED:
                    return True

                # Only users who has change permission can view unpublished comments
                return user_obj.has_perm(f"{app_label}.change_comment", obj)

        if perm in [f"{app_label}.change_comment", f"{app_label}.delete_comment"]:
            if isinstance(obj, Comment):
                if obj.target and not getattr(obj.target, "is_comments_enabled", True):
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

        if perm == f"{app_label}.add_comment_with_profile" and obj:
            return user_obj.has_perm(f"{profile_app_label}.use_profile", obj)
