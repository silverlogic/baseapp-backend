from typing import Any

from django.core.checks import Error, Tags, register
from django.core.files.storage import Storage

from .storage import _is_s3_storage, files_storage_is_private, get_wrapped_files_storage

PUBLIC_ACLS = {"public-read", "public-read-write"}


def private_storage_errors(storage: Storage) -> list[Error]:
    """
    Ways a files storage that signs its URLs can still hand out public ones. Signing alone
    does not make files private: the objects themselves must not be publicly readable.
    """
    if not (_is_s3_storage(storage) and files_storage_is_private(storage)):
        return []

    errors = []
    if getattr(storage, "custom_domain", None) and not getattr(storage, "cloudfront_signer", None):
        errors.append(
            Error(
                "The private files storage has a custom_domain but no cloudfront_signer, so "
                "django-storages returns unsigned, permanent URLs for it.",
                hint="Remove custom_domain from that storage, or configure "
                "cloudfront_key_id/cloudfront_key for signed CloudFront URLs.",
                id="baseapp_files.E001",
            )
        )

    acls = {getattr(storage, "default_acl", None)}
    get_object_parameters = getattr(storage, "get_object_parameters", None)
    if get_object_parameters:
        acls.add(get_object_parameters("files/check").get("ACL"))
    if acls & PUBLIC_ACLS:
        errors.append(
            Error(
                "The private files storage uploads objects with a public ACL, so they are "
                "readable without a signed URL.",
                hint='Set default_acl (and any AWS_S3_OBJECT_PARAMETERS ACL) to "private" and '
                "block public access on the bucket.",
                id="baseapp_files.E002",
            )
        )
    return errors


@register(Tags.security)
def check_private_files_storage(app_configs: Any = None, **kwargs: Any) -> list[Error]:
    return private_storage_errors(get_wrapped_files_storage())
