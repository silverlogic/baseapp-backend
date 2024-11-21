import graphene
import swapper

from django import forms
from graphene_django.types import ErrorType
from graphene_django.forms.mutation import _set_errors_flag_to_context


from baseapp_core.graphql import RelayMutation, login_required
from django import forms
from graphene_django.forms.mutation import _set_errors_flag_to_context
from graphene_django.types import ErrorType

from baseapp.content_feed.models import SwappedContentPost as ContentPost

from .object_types import ContentPostObjectType

from baseapp.content_feed.models import SwappedContentPost as ContentPost
ContentPostImage = swapper.load_model("baseapp_content_feed", "ContentPostImage")

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
        content = input.get("content")
        images = input.get("images", [])

        if form.is_valid():
            instance = form.save(commit=False)
            instance.user = info.context.user
            instance.profile = info.context.user.profile
            instance.save()

            for image in images:
                ContentPostImage.objects.create(image=info.context._files[image], post=instance)

            return ContentPostCreate(
                content_post=ContentPostObjectType._meta.connection.Edge(node=instance),
            )
        else:
            errors = ErrorType.from_errors(form.errors)
            _set_errors_flag_to_context(info)

            return cls(errors=errors)


class ContentFeedMutations(object):
    content_post_create = ContentPostCreate.Field()
