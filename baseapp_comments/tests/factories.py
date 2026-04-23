import factory
import swapper

from baseapp_core.models import DocumentId

Comment = swapper.load_model("baseapp_comments", "Comment")


def get_content_type(field_name):
    def _obj_content_type(obj):
        if not hasattr(obj, field_name):
            return None
        target = getattr(obj, field_name, None)
        if target:
            return DocumentId.get_or_create_for_object(target).content_type
        return None

    return _obj_content_type


def get_obj_pk(field_name):
    def _obj_id(obj):
        if not hasattr(obj, field_name):
            return None
        target = getattr(obj, field_name, None)
        if target:
            return target.pk
        return None

    return _obj_id


def get_document_id(field_name):
    def _doc_id(obj):
        if not hasattr(obj, field_name):
            return None
        target = getattr(obj, field_name, None)
        if target:
            return DocumentId.get_or_create_for_object(target)
        return None

    return _doc_id


class AbstractCommentFactory(factory.django.DjangoModelFactory):
    user = factory.SubFactory("baseapp_core.tests.factories.UserFactory")
    body = factory.Faker("text")

    class Meta:
        abstract = True

    target_document = factory.LazyAttribute(get_document_id("target"))

    def __setattr__(self, name, value):
        super().__setattr__(name, value)

        if name in ["target"]:
            setattr(self, "target_document", DocumentId.get_or_create_for_object(value))


class CommentFactory(AbstractCommentFactory):
    class Meta:
        model = Comment

    @factory.post_generation
    def is_comments_enabled(obj, create, extracted, **kwargs):
        """
        Set is_comments_enabled on the CommentableMetadata associated with this comment.
        Usage: CommentFactory(is_comments_enabled=False)
        """
        if extracted is None or not create:
            return

        CommentableMetadata = swapper.load_model("baseapp_comments", "CommentableMetadata")
        metadata = CommentableMetadata.get_or_create_for_object(obj)
        if metadata:
            metadata.is_comments_enabled = extracted
            metadata.save(update_fields=["is_comments_enabled"])
