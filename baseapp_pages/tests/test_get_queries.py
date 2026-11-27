from unittest.mock import MagicMock

import pytest
import swapper

from baseapp_core.tests.factories import UserFactory
from baseapp_pages.graphql.object_types import URLPathNode, get_view_permission
from baseapp_pages.models import URLPath

from .factories import PageFactory, URLPathFactory
from .utils import make_text_into_quill

pytestmark = pytest.mark.django_db

Page = swapper.load_model("baseapp_pages", "Page")
page_app_label = Page._meta.app_label

GET_PAGE_BY_PATH = """
    query Page($path: String!) {
        urlPath(path: $path) {
            path
            target {
                id

                metadata {
                    metaTitle
                }

                ... on Page {
                    pk
                    title
                    body
                    user {
                        id
                        fullName
                        firstName
                        profile {
                            id
                            name
                        }
                    }
                }
            }
        }
    }
"""


def test_fallback_meta_title(django_user_client, graphql_user_client) -> None:
    page = PageFactory(user=django_user_client.user)
    url_path = URLPathFactory(target=page, language="en", path="/test-page/", is_active=True)

    response = graphql_user_client(GET_PAGE_BY_PATH, variables={"path": url_path.path})

    content = response.json()
    assert content["data"]["urlPath"]["target"]["id"] == page.relay_id
    assert content["data"]["urlPath"]["target"]["metadata"]["metaTitle"] == page.title


def test_return_active_url_path(django_user_client, graphql_user_client) -> None:
    page = PageFactory(user=django_user_client.user)
    deactivated_url_path = URLPathFactory(
        target=page, language="en", path="/deactivated/", is_active=False
    )
    activated_url_path = URLPathFactory(
        target=page, language="en", path="/activated/", is_active=True
    )

    response = graphql_user_client(GET_PAGE_BY_PATH, variables={"path": deactivated_url_path.path})

    content = response.json()
    assert content["data"]["urlPath"]["path"] == activated_url_path.path


def test_active_url_path_no_language(django_user_client, graphql_user_client) -> None:
    page = PageFactory(user=django_user_client.user)
    url_path = URLPathFactory(target=page, language=None, path="/test-page/", is_active=True)

    response = graphql_user_client(GET_PAGE_BY_PATH, variables={"path": url_path.path})

    content = response.json()
    assert content["data"]["urlPath"]["path"] == url_path.path


def test_active_url_path_on_object_type(django_user_client, graphql_user_client) -> None:
    page = PageFactory(user=django_user_client.user)
    URLPathFactory(target=page, language=None, path="/old-test-page/", is_active=False)
    url_path = URLPathFactory(target=page, language=None, path="/test-page/", is_active=True)

    response = graphql_user_client(
        query="""
            query Page($id: ID!) {
                page(id: $id) {
                    urlPath {
                        id
                        path
                    }
                }
            }
        """,
        variables={"id": page.relay_id},
    )

    content = response.json()
    assert content["data"]["page"]["urlPath"]["path"] == url_path.path


def test_deliver_localized_title_and_body(django_user_client, graphql_user_client) -> None:
    title_en = "About"
    body_en = "This is the about page"
    title_pt = "Sobre"
    body_pt = "Esta é a página sobre"

    page = PageFactory(
        user=django_user_client.user,
        title_en=title_en,
        body_en=make_text_into_quill(body_en),
        title_pt=title_pt,
        body_pt=make_text_into_quill(body_pt),
    )

    response = graphql_user_client(
        query="""
            query Page($id: ID!) {
                page(id: $id) {
                    title
                    body
                }
            }
        """,
        variables={"id": page.relay_id},
        headers={"HTTP_ACCEPT_LANGUAGE": "pt"},
    )

    content = response.json()

    assert content["data"]["page"]["title"] == title_pt
    assert content["data"]["page"]["body"] == body_pt


def test_deliver_localized_title_and_body_by_path(django_user_client, graphql_user_client) -> None:
    title_en = "About"
    body_en = "This is the about page"
    title_pt = "Sobre"
    body_pt = "Esta é a página sobre"

    page = PageFactory(
        user=django_user_client.user,
        title_en=title_en,
        body_en=make_text_into_quill(body_en),
        title_pt=title_pt,
        body_pt=make_text_into_quill(body_pt),
    )
    url_path = URLPathFactory(target=page, language="pt", path="/sobre", is_active=True)

    response = graphql_user_client(
        query=GET_PAGE_BY_PATH,
        variables={"path": url_path.path},
        headers={"HTTP_ACCEPT_LANGUAGE": "pt"},
    )

    content = response.json()

    assert content["data"]["urlPath"]["target"]["metadata"]["metaTitle"] == title_pt
    assert content["data"]["urlPath"]["target"]["title"] == title_pt
    assert content["data"]["urlPath"]["target"]["body"] == body_pt


def test_anon_can_view_page(graphql_client) -> None:
    page = PageFactory()

    response = graphql_client(
        query="""
            query Page($id: ID!) {
                page(id: $id) {
                    pk
                }
            }
        """,
        variables={"id": page.relay_id},
    )

    content = response.json()

    assert content["data"]["page"]["pk"] == page.pk


def test_owner_can_view_unpublished_page(django_user_client, graphql_user_client) -> None:
    page = PageFactory(user=django_user_client.user, status=Page.PageStatus.DRAFT)

    response = graphql_user_client(
        query="""
            query Page($id: ID!) {
                page(id: $id) {
                    pk
                }
            }
        """,
        variables={"id": page.relay_id},
    )

    content = response.json()

    assert content["data"]["page"]["pk"] == page.pk


def test_anon_cant_view_unpublished_page(graphql_client) -> None:
    page = PageFactory(status=Page.PageStatus.DRAFT)

    response = graphql_client(
        query="""
            query Page($id: ID!) {
                page(id: $id) {
                    pk
                }
            }
        """,
        variables={"id": page.relay_id},
    )

    content = response.json()

    assert content["data"]["page"] is None


def test_another_user_cant_view_unpublished_page(graphql_user_client) -> None:
    page = PageFactory(status=Page.PageStatus.DRAFT)

    response = graphql_user_client(
        query="""
            query Page($id: ID!) {
                page(id: $id) {
                    pk
                }
            }
        """,
        variables={"id": page.relay_id},
    )

    content = response.json()

    assert content["data"]["page"] is None


def test_anon_cant_view_unpublished_page_by_url(graphql_client) -> None:
    page = PageFactory(status=Page.PageStatus.DRAFT)
    url_path = URLPathFactory(target=page, language="en", path="/test-page/", is_active=True)

    response = graphql_client(GET_PAGE_BY_PATH, variables={"path": url_path.path})

    content = response.json()
    assert content["data"]["urlPath"]["target"] is None


def test_user_cant_view_unpublished_page_by_url(graphql_user_client) -> None:
    page = PageFactory(status=Page.PageStatus.DRAFT)
    url_path = URLPathFactory(target=page, language="en", path="/test-page/", is_active=True)

    response = graphql_user_client(GET_PAGE_BY_PATH, variables={"path": url_path.path})

    content = response.json()
    assert content["data"]["urlPath"]["target"] is None


def test_owner_can_view_unpublished_page_by_url(django_user_client, graphql_user_client) -> None:
    page = PageFactory(user=django_user_client.user, status=Page.PageStatus.DRAFT)
    url_path = URLPathFactory(target=page, language="en", path="/test-page/", is_active=True)

    response = graphql_user_client(GET_PAGE_BY_PATH, variables={"path": url_path.path})

    content = response.json()
    assert content["data"]["urlPath"]["target"]["pk"] == page.pk


def test_owner_can_change_page(django_user_client, graphql_user_client) -> None:
    page = PageFactory(
        user=django_user_client.user,
    )

    response = graphql_user_client(
        query=f"""
            query Page($id: ID!) {{
                page(id: $id) {{
                    canChange: hasPerm(perm: "change")
                    canDelete: hasPerm(perm: "delete")
                    canChangeFull: hasPerm(perm: "{page_app_label}.change_page")
                    canDeleteFull: hasPerm(perm: "{page_app_label}.delete_page")
                }}
            }}
        """,
        variables={"id": page.relay_id},
    )

    content = response.json()

    assert content["data"]["page"]["canChange"]
    assert content["data"]["page"]["canDelete"]
    assert content["data"]["page"]["canChangeFull"]
    assert content["data"]["page"]["canDeleteFull"]


def test_another_user_cant_change_page(graphql_user_client) -> None:
    page = PageFactory()

    response = graphql_user_client(
        query="""
            query Page($id: ID!) {
                page(id: $id) {
                    canChange: hasPerm(perm: "change")
                    canDelete: hasPerm(perm: "delete")
                    canChangeFull: hasPerm(perm: "baseapp_pages.change_page")
                    canDeleteFull: hasPerm(perm: "baseapp_pages.delete_page")
                }
            }
        """,
        variables={"id": page.relay_id},
    )

    content = response.json()

    assert not content["data"]["page"]["canChange"]
    assert not content["data"]["page"]["canDelete"]
    assert not content["data"]["page"]["canChangeFull"]
    assert not content["data"]["page"]["canDeleteFull"]


GET_USER_BY_PATH = """
    query User($path: String!) {
        urlPath(path: $path) {
            target {
                __typename
                ... on User {
                    id
                }
            }
        }
    }
"""


def test_anon_can_view_user_by_url(graphql_client) -> None:
    # `view_user` is granted to everyone, so a user target stays visible.
    user = UserFactory()
    url_path = URLPathFactory(target=user, language="en", path="/some-user/", is_active=True)

    response = graphql_client(GET_USER_BY_PATH, variables={"path": url_path.path})

    content = response.json()
    assert content["data"]["urlPath"]["target"] == {"__typename": "User", "id": user.relay_id}


def test_view_permission_of_page_target() -> None:
    assert get_view_permission(PageFactory()) == f"{page_app_label}.view_page"


def test_view_permission_of_other_targets_is_the_model_view_permission() -> None:
    user = UserFactory()

    assert get_view_permission(user) == f"{user._meta.app_label}.view_user"


def test_url_path_target_is_hidden_without_its_view_permission() -> None:
    # Any target model is gated, not only pages: with the permission denied it is not returned.
    user = UserFactory()
    url_path = URLPathFactory(target=user, language="en", path="/some-user/", is_active=True)
    info = MagicMock()
    info.context.user.has_perm.return_value = False

    assert URLPathNode.resolve_target(url_path, info) is None
    info.context.user.has_perm.assert_called_once_with(f"{user._meta.app_label}.view_user", user)


def test_url_path_without_target_resolves_to_none() -> None:
    info = MagicMock()

    assert URLPathNode.resolve_target(URLPath(path="/orphan/"), info) is None
    info.context.user.has_perm.assert_not_called()
