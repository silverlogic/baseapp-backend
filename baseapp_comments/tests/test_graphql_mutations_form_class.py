import graphene
import pytest
import swapper
from django.test import RequestFactory
from graphene_django.settings import graphene_settings

from baseapp_comments.graphql.mutations import (
    CommentCreate,
    CommentForm,
    CommentsMutations,
    CommentUpdate,
)

from .factories import CommentFactory

pytestmark = pytest.mark.django_db

Comment = swapper.load_model("baseapp_comments", "Comment")


class CommentWithLanguageForm(CommentForm):
    class Meta(CommentForm.Meta):
        fields = ("body", "language")


class CommentWithLanguageCreate(CommentCreate):
    class Input(CommentCreate.Input):
        language = graphene.String(required=False)

    class Meta:
        name = "CommentCreatePayload"

    @classmethod
    def get_form_class(cls) -> type[CommentForm]:
        return CommentWithLanguageForm


class CommentWithLanguageUpdate(CommentUpdate):
    class Input(CommentUpdate.Input):
        language = graphene.String(required=True)

    class Meta:
        name = "CommentUpdatePayload"

    @classmethod
    def get_form_class(cls) -> type[CommentForm]:
        return CommentWithLanguageForm


class Mutation(graphene.ObjectType, CommentsMutations):
    # Declared on the root Mutation, so they replace the package's fields of the same name.
    comment_create = CommentWithLanguageCreate.Field()
    comment_update = CommentWithLanguageUpdate.Field()


schema = graphene.Schema(query=graphene_settings.SCHEMA.query, mutation=Mutation)

COMMENT_CREATE_GRAPHQL = """
    mutation CommentCreate($input: CommentCreateInput!) {
        commentCreate(input: $input) {
            comment { node { id body } }
            errors { field messages }
        }
    }
"""

COMMENT_UPDATE_GRAPHQL = """
    mutation CommentUpdate($input: CommentUpdateInput!) {
        commentUpdate(input: $input) {
            comment { id body }
            errors { field messages }
        }
    }
"""


def _execute(query: str, variables: dict, user) -> dict:
    request = RequestFactory().post("/graphql")
    user.current_profile = user.profile
    request.user = user
    result = schema.execute(query, variables=variables, context_value=request)
    assert result.errors is None, result.errors
    return result.data


def test_default_form_class() -> None:
    assert CommentCreate.get_form_class() is CommentForm
    assert CommentUpdate.get_form_class() is CommentForm


def test_subclass_keeps_the_input_type_names() -> None:
    create_input = schema.graphql_schema.get_type("CommentCreateInput")
    update_input = schema.graphql_schema.get_type("CommentUpdateInput")

    assert {"targetObjectId", "body", "language"} <= set(create_input.fields)
    assert {"id", "body", "language"} <= set(update_input.fields)
    assert schema.graphql_schema.get_type("CommentCreatePayload") is not None
    assert schema.graphql_schema.get_type("CommentUpdatePayload") is not None


def test_create_saves_the_extra_field(django_user_client) -> None:
    target = CommentFactory()

    data = _execute(
        COMMENT_CREATE_GRAPHQL,
        {"input": {"targetObjectId": target.relay_id, "body": "olá", "language": "pt"}},
        django_user_client.user,
    )

    assert data["commentCreate"]["errors"] is None
    comment = Comment.objects.get(body="olá")
    assert comment.language == "pt"


def test_update_saves_the_extra_field(django_user_client) -> None:
    comment = CommentFactory(user=django_user_client.user, language="en")

    data = _execute(
        COMMENT_UPDATE_GRAPHQL,
        {"input": {"id": comment.relay_id, "body": "hola", "language": "es"}},
        django_user_client.user,
    )

    assert data["commentUpdate"]["errors"] is None
    comment.refresh_from_db()
    assert (comment.body, comment.language, comment.is_edited) == ("hola", "es", True)


def test_default_mutation_ignores_fields_outside_its_form(
    django_user_client, graphql_user_client
) -> None:
    comment = CommentFactory(user=django_user_client.user, language="en")

    graphql_user_client(
        COMMENT_UPDATE_GRAPHQL.replace("errors { field messages }", "errors { field }"),
        variables={"input": {"id": comment.relay_id, "body": "edited"}},
    )

    comment.refresh_from_db()
    assert (comment.body, comment.language) == ("edited", "en")
