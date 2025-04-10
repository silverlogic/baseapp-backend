import graphene
import swapper
from django import forms
from graphene_django.forms.mutation import _set_errors_flag_to_context
from graphene_django.types import ErrorType

from baseapp_core.graphql import RelayMutation, login_required

ContentPost = swapper.load_model(
    "baseapp_content_feed", "ContentPost", required=False, require_ready=False
)
ContentPostImage = swapper.load_model("baseapp_content_feed", "ContentPostImage")

ContentPostObjectType = ContentPost.get_graphql_object_type()

ContentPostImageType = ContentPostImage.get_graphql_object_type()


class ContentPostForm(forms.ModelForm):
    class Meta:
        model = ContentPost
        fields = ("content",)


class ContentPostCreate(RelayMutation):
    content_post = graphene.Field(ContentPostObjectType._meta.connection.Edge)

    class Input:
        content = graphene.String(required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        form = ContentPostForm(data=input)
        images = [v for k, v in info.context.FILES.items() if k.startswith("images")]

        if form.is_valid():
            instance = form.save(commit=False)
            instance.user = info.context.user
            instance.profile = info.context.user.current_profile
            instance.save()

            created_images_list = []

            for image in images:
                created_images_list.append(
                    ContentPostImage.objects.create(image=image, post=instance)
                )

            instance.refresh_from_db()

            return ContentPostCreate(
                content_post=ContentPostObjectType._meta.connection.Edge(node=instance),
            )
        else:
            errors = ErrorType.from_errors(form.errors)
            _set_errors_flag_to_context(info)

            return cls(errors=errors)


class ContentFeedMutations(object):
    content_post_create = ContentPostCreate.Field()
