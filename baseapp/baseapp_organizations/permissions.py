import swapper
from django.contrib.auth.backends import BaseBackend

Organization = swapper.load_model("baseapp_organizations", "Organization")
app_label = Organization._meta.app_label


class OrganizationsPermissionsBackend(BaseBackend):
    def has_perm(self, user_obj, perm, obj=None):
        if perm in [f"{app_label}.add_organization"]:
            return user_obj.is_authenticated
