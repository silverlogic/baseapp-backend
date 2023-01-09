def get_permission_loader(permissions):
    def load_permissions_data(apps, schema_editor):
        Permission = apps.get_model("auth", "Permission")
        Group = apps.get_model("auth", "Group")
        for perm_group in permissions:
            group, _ = Group.objects.get_or_create(name=perm_group["name"])
            if perm_group.get("permissions"):
                for perm in perm_group["permissions"]:
                    permission = Permission.objects.filter(
                        codename=perm
                    ).first()
                    if permission:
                        group.permissions.add(permission)
    return load_permissions_data


def get_permission_remover(permissions, remove_group=False):
    def remove_permissions_data(apps, schema_editor):
        """
        The group will not be deleted if the the model is not passed as an argument
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
