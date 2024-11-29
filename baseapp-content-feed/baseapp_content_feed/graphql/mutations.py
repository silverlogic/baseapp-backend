import graphene
import swapper

from baseapp_core.graphql import RelayMutation,SerializerMutation, login_required
from django import forms
from django.utils.translation import gettext_lazy as _
from graphene_django.forms.mutation import _set_errors_flag_to_context
from graphene_django.types import ErrorType
from graphql.error import GraphQLError

from baseapp_content_feed.models import SwappedContentPost as ContentPost
from baseapp_content_feed.models import SwappedContentPostImage as ContentPostImage

from .object_types import ContentPostImageObjectType, ContentPostObjectType
from rest_framework import serializers


class ContentPostForm(forms.ModelForm):
    class Meta:
        model = ContentPost
        fields = ("content",)


class ContentPostCreate(RelayMutation):
    content_post = graphene.Field(ContentPostObjectType._meta.connection.Edge)

    class Input:
        content = graphene.String(required=True)
        images = graphene.List(graphene.String)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        content = input.get("content")
        images = input.get("images", [])

        form = ContentPostForm(data={**input, "author": info.context.user})
        if form.is_valid():
            instance = form.save(commit=False)
            instance.author = info.context.user
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


class BaseContentPostImageSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(required=True)
    post = serializers.PrimaryKeyRelatedField(queryset=ContentPost.objects.all())

    class Meta:
        model = ContentPostImage
        fields = ("image", "post")

class ContentPostImageCreateSerializer(BaseContentPostImageSerializer):

    def create(self, validated_data):
        instance = super().create(validated_data,{"image": validated_data['image']})
        return instance
    
class ContentPostImageCreate(SerializerMutation):
    content_post_image = graphene.Field(
        lambda: ContentPostImageObjectType._meta.connection.Edge
    )

    class Meta:
        serializer_class = ContentPostImageCreateSerializer

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        if not info.context.user.has_perm("baseapp_content_feed.add_contentpostimage"):
            raise GraphQLError(
                "You don't have permission to perform this action.",
                extensions={"code": "permission_required"},
            )

        return super().mutate_and_get_payload(root, info, **input)

    @classmethod
    def perform_mutate(cls, serializer, info):
        obj = serializer.save()
        return cls(
            errors=None,
            content_post_image=ContentPostImageObjectType._meta.connection.Edge(
                node=obj
            ),
        )


class ContentPostMutations(object):
    profile_create = ContentPostImageCreate.Field()
