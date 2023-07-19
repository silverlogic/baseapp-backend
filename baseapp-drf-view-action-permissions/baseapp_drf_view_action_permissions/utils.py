from ipware import get_client_ip

from .models import IpRestriction
from .settings import PermissionSettings


def get_permission_loader(permissions):
    def load_permissions_data(apps, schema_editor):
        Permission = apps.get_model("auth", "Permission")
        Group = apps.get_model("auth", "Group")
        for perm_group in permissions:
            group, _ = Group.objects.get_or_create(name=perm_group["name"])
            if perm_group.get("permissions"):
                for perm in perm_group["permissions"]:
                    permission = Permission.objects.filter(codename=perm).first()
                    if permission:
                        group.permissions.add(permission)

    return load_permissions_data


def get_permission_remover(permissions, remove_group=False):
    def remove_permissions_data(apps, schema_editor):
        """
        The group will not be deleted if the remove_group is False
        """
        Permission = apps.get_model("auth", "Permission")
        Group = apps.get_model("auth", "Group")
        db_alias = schema_editor.connection.alias
        for perm_group in permissions:
            group = Group.objects.using(db_alias).filter(name=perm_group["name"]).first()
            if group:
                for perm in perm_group.get("permissions", []):
                    permission = Permission.objects.using(db_alias).filter(codename=perm).first()
                    if permission:
                        group.permissions.remove(permission)
                if remove_group:
                    group.delete()

    return remove_permissions_data


def client_ip_address_is_restricted(request):
    """
    Check if the client IP address is restricted
    """
    permission_settings = PermissionSettings()
    client_ip, _ = get_client_ip(request)
    restricted = (
        IpRestriction.objects.filter(ip_address=client_ip)
        .prefetch_related("unrestricted_roles")
        .first()
    )
    if permission_settings.ALLOW_ONLY_WHITELISTED_IP:
        if (restricted and not restricted.is_whitelisted) or not restricted:
            return True
    else:
        if restricted and not restricted.is_whitelisted:
            try:
                if (
                    request.user
                    and not restricted.unrestricted_roles.filter(id=request.user.role_id).exists()
                ) or not request.user:
                    return True
            except Exception:
                return True
    return False
