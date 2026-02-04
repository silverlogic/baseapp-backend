def normalize_permission(perm, model):
    """
    Normalize a permission string into `app_label.codename`.

    Supported inputs:
    - "users.change_user"
    - "change"
    - "change_user"

    Requires a Django model instance or model class.
    """
    if "." in perm:
        return perm

    opts = model._meta

    if "_" not in perm:
        codename = f"{perm}_{opts.model_name}"
    else:
        codename = perm

    return f"{opts.app_label}.{codename}"
