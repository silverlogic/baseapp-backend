import swapper
from django.contrib.auth.backends import BaseBackend

File = swapper.load_model("baseapp_files", "File")
file_app_label = File._meta.app_label
file_model_name = File._meta.model_name.lower()


class FilesPermissionsBackend(BaseBackend):
    def authenticate(self, request, **kwargs):
        return None

    def has_perm(self, user_obj, perm, obj=None):
        if perm == f"{file_app_label}.attach_{file_model_name}":
            if obj:
                return obj.created_by == user_obj
            return False

        if perm == f"{file_app_label}.view_{file_model_name}":
            if obj:
                # Owner can view their own files
                if obj.created_by == user_obj:
                    return True
                # Check if user has global permission (for admins with view_file perm)
                # This is needed because ModelBackend doesn't grant global perms with obj
                if user_obj.has_perm(perm):
                    return True
                return False
            return False

        if perm == f"{file_app_label}.change_{file_model_name}":
            if obj:
                # Owner can change their own files
                if obj.created_by == user_obj:
                    return True
                # Check if user has global permission (for admins with change_file perm)
                # This is needed because ModelBackend doesn't grant global perms with obj
                if user_obj.has_perm(perm):
                    return True
                return False
            return False

        if perm == f"{file_app_label}.delete_{file_model_name}":
            if obj:
                # Owner can delete their own files
                if obj.created_by == user_obj:
                    return True
                # Check if user has global permission (for admins with delete_file perm)
                # This is needed because ModelBackend doesn't grant global perms with obj
                if user_obj.has_perm(perm):
                    return True
                return False
            return False

        return False
