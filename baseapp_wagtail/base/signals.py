from django.dispatch import receiver
from wagtail.signals import page_published, page_unpublished, post_page_move

from baseapp_wagtail.base.urlpath.urlpath_sync import WagtailURLPathSync
from baseapp_wagtail.base.metadata.metadata_sync import WagtailMetadataSync


@receiver(page_published)
def update_urlpath_on_publish(sender, instance, revision, **kwargs):
    if instance.scheduled_revision:
        WagtailURLPathSync(instance).create_or_update_urlpath_draft()
    else:
        WagtailURLPathSync(instance).publish_urlpath()


@receiver(page_published)
def update_metadata_on_publish(sender, instance, revision, **kwargs):
    WagtailMetadataSync(instance).create_or_update_metadata()


@receiver(post_page_move)
def update_urlpath_on_move(sender, instance, **kwargs):
    WagtailURLPathSync(instance.specific).update_urlpath()


@receiver(post_page_move)
def update_metadata_on_move(sender, instance, **kwargs):
    WagtailMetadataSync(instance.specific).create_or_update_metadata()


@receiver(page_unpublished)
def deactivate_urlpath_on_unpublish(sender, instance, **kwargs):
    WagtailURLPathSync(instance).deactivate_urlpath()


@receiver(page_unpublished)
def delete_metadata_on_unpublish(sender, instance, **kwargs):
    WagtailMetadataSync(instance).delete_metadata()
