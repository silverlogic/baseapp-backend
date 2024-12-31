import graphene

from django import forms
from graphene_django.types import ErrorType
from graphene_django.forms.mutation import _set_errors_flag_to_context


from baseapp_core.graphql import RelayMutation, login_required
from baseapp_content_feed.models import SwappedContentPost as ContentPost
from django.utils.translation import gettext_lazy as _

from .object_types import ContentPostObjectType

from baseapp_content_feed.models import SwappedContentPost as ContentPost

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
        content = input.get("content")

        # content_post = ContentPost.objects.create(
        #     author=info.context.user,
        #     content=content
        # )

        form = ContentPostForm(data={
            **input,
            "author": info.context.user
        })
        if form.is_valid():
            instance = form.save(commit=False)
            instance.author = info.context.user
            instance.save()

            return ContentPostCreate(
                content_post=ContentPostObjectType._meta.connection.Edge(node=instance),
            )
        else:
            errors = ErrorType.from_errors(form.errors)
            _set_errors_flag_to_context(info)

            return cls(errors=errors)


class ContentFeedMutations(object):
    content_post_create = ContentPostCreate.Field()
