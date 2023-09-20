import swapper
from django.db.models.signals import post_delete, post_save

from .utils import recalculate_files_count

File = swapper.load_model("baseapp_files", "File")


def update_files_count(sender, instance, created=False, **kwargs):
    parent = instance.parent
    if parent:
        recalculate_files_count(parent)


post_save.connect(update_files_count, sender=File, dispatch_uid="update_files_count")
post_delete.connect(update_files_count, sender=File, dispatch_uid="update_files_count")
