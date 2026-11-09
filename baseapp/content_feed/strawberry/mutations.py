import strawberry
import swapper
from django import forms
from django.apps import apps
from django.db import transaction
from rest_framework import serializers
from strawberry import UNSET
from strawberry.types import Info

from baseapp_core.plugins import shared_services
from baseapp_core.strawberry import (
    RelayMutationInput,
    RelayMutationPayload,
    type_for_model,
)
from baseapp_core.strawberry.connections import Edge
from baseapp_core.strawberry.mutations import ErrorType, input_data, relay_mutation

ContentPost = swapper.load_model("baseapp_content_feed", "ContentPost")
ContentPostImage = swapper.load_model("baseapp_content_feed", "ContentPostImage")


class ContentPostForm(forms.ModelForm):
    class Meta:
        model = ContentPost
        fields = ("content",)


class ImageSerializer(serializers.Serializer):
    image = serializers.ImageField(required=False, allow_null=True)


@strawberry.input(name="ContentPostCreateInput")
class ContentPostCreateInput(RelayMutationInput):
    content: str
    is_reactions_enabled: bool
    mentioned_profile_ids: list[strawberry.ID | None] | None = UNSET


@strawberry.type(name="ContentPostCreatePayload")
class ContentPostCreatePayload(RelayMutationPayload):
    content_post: Edge[type_for_model(ContentPost)] | None = None


@strawberry.type
class ContentFeedMutations:
    @relay_mutation(login_required=True)
    def content_post_create(
        self, info: Info, input: ContentPostCreateInput
    ) -> ContentPostCreatePayload | None:
        data = input_data(input)
        mentioned_profile_ids = data.pop("mentioned_profile_ids", None) or []
        form = ContentPostForm(data=data)
        images = [v for k, v in info.context.FILES.items() if k.startswith("images")]

        if not form.is_valid():
            return ContentPostCreatePayload(
                errors=[
                    ErrorType(field=field, messages=list(messages))
                    for field, messages in form.errors.items()
                ]
            )

        with transaction.atomic():
            instance = form.save(commit=False)
            instance.user = info.context.user
            if apps.is_installed("baseapp_profiles") and hasattr(instance, "profile"):
                instance.profile = info.context.user.current_profile
            instance.save()

            if (service := shared_services.get("reactable_metadata")) is not None:
                service.set_is_reactions_enabled(instance, data["is_reactions_enabled"])

            for image in images:
                serializer = ImageSerializer(data={"image": image})
                if not serializer.is_valid():
                    return ContentPostCreatePayload(
                        errors=[
                            ErrorType(
                                field="images",
                                messages=[str(m) for m in serializer.errors["image"]],
                            )
                        ]
                    )
                ContentPostImage.objects.create(
                    image=serializer.validated_data["image"], post=instance
                )

            if mentioned_profile_ids:
                if service := shared_services.get("mentions"):
                    service.update_mentions(
                        instance,
                        mentioned_profile_ids,
                        exclude_profile=getattr(info.context.user, "current_profile", None),
                    )

            instance.refresh_from_db()

            return ContentPostCreatePayload(content_post=Edge(node=instance, cursor=None))
