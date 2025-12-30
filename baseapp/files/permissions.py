import swapper
from django.contrib.auth.backends import BaseBackend
from django.db import models

File = swapper.load_model("baseapp_files", "File")
file_app_label = File._meta.app_label
file_model_name = File._meta.model_name.lower()


class FilesPermissionsBackend(BaseBackend):
    def has_perm(self, user_obj, perm, obj=None):
        if obj and perm == f"{file_app_label}.attach_{file_model_name}":
            return obj.created_by == user_obj
