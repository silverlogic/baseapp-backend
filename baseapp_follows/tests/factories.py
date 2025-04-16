import factory
import swapper
from django.contrib.contenttypes.models import ContentType


class FollowFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = swapper.load_model("baseapp_follows", "Follow")
        abstract = True

    actor_content_type = factory.LazyAttribute(lambda o: ContentType.objects.get_for_model(o.actor))
    actor_object_id = factory.SelfAttribute("actor.id")

    target_content_type = factory.LazyAttribute(
        lambda o: ContentType.objects.get_for_model(o.target)
    )
    target_object_id = factory.SelfAttribute("target.id")

    target_is_following_back = False

    @factory.post_generation
    def actor(self, create, extracted, **kwargs):
        if not create:
            return

        if extracted:
            self.actor = extracted
            self.actor_content_type = ContentType.objects.get_for_model(extracted)
            self.actor_object_id = extracted.id
            self.save()

    @factory.post_generation
    def target(self, create, extracted, **kwargs):
        if not create:
            return

        if extracted:
            self.target = extracted
            self.target_content_type = ContentType.objects.get_for_model(extracted)
            self.target_object_id = extracted.id
            self.save()
