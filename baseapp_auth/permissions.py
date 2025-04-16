from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend

User = get_user_model()

private_field_perms = [
    f"{User._meta.app_label}.view_user_email",
    f"{User._meta.app_label}.view_user_phone_number",
    f"{User._meta.app_label}.view_user_is_superuser",
    f"{User._meta.app_label}.view_user_is_staff",
    f"{User._meta.app_label}.view_user_is_email_verified",
    f"{User._meta.app_label}.view_user_password_changed_date",
    f"{User._meta.app_label}.view_user_new_email",
    f"{User._meta.app_label}.view_user_is_new_email_confirmed",
]


class UsersPermissionsBackend(BaseBackend):
    def has_perm(self, user_obj, perm, obj=None):
        if perm == f"{User._meta.app_label}.view_user":
            # every body can view all users
            # TO DO: maybe check if user is_active
            return True

        if perm == f"{User._meta.app_label}.view_all_users":
            return True

        if perm in private_field_perms and obj is not None:
            if (
                isinstance(obj, User)
                and user_obj.is_authenticated
                and (obj.pk == user_obj.pk or (user_obj.is_superuser or user_obj.is_staff))
            ):
                return True
            else:
                # Anyone with permission set also can:
                return user_obj.has_perm(perm)
