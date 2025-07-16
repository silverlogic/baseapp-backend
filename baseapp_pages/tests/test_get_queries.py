import pytest
import swapper

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

                ... on BAPage {
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


def test_fallback_meta_title(django_user_client, graphql_user_client):
    page = PageFactory(user=django_user_client.user)
    url_path = URLPathFactory(target=page, language="en", path="/test-page/", is_active=True)

    response = graphql_user_client(GET_PAGE_BY_PATH, variables={"path": url_path.path})

    content = response.json()
    assert content["data"]["urlPath"]["target"]["id"] == page.relay_id
    assert content["data"]["urlPath"]["target"]["metadata"]["metaTitle"] == page.title


def test_return_active_url_path(django_user_client, graphql_user_client):
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


def test_active_url_path_no_language(django_user_client, graphql_user_client):
    page = PageFactory(user=django_user_client.user)
    url_path = URLPathFactory(target=page, language=None, path="/test-page/", is_active=True)

    response = graphql_user_client(GET_PAGE_BY_PATH, variables={"path": url_path.path})

    content = response.json()
    assert content["data"]["urlPath"]["path"] == url_path.path


def test_active_url_path_on_object_type(django_user_client, graphql_user_client):
    page = PageFactory(user=django_user_client.user)
    URLPathFactory(target=page, language=None, path="/old-test-page/", is_active=False)
    url_path = URLPathFactory(target=page, language=None, path="/test-page/", is_active=True)

    response = graphql_user_client(
        query="""
            query Page($id: ID!) {
                baPage(id: $id) {
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
    assert content["data"]["baPage"]["urlPath"]["path"] == url_path.path


def test_deliver_localized_title_and_body(django_user_client, graphql_user_client):
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
                baPage(id: $id) {
                    title
                    body
                }
            }
        """,
        variables={"id": page.relay_id},
        headers={"HTTP_ACCEPT_LANGUAGE": "pt"},
    )

    content = response.json()

    assert content["data"]["baPage"]["title"] == title_pt
    assert content["data"]["baPage"]["body"] == body_pt


def test_deliver_localized_title_and_body_by_path(django_user_client, graphql_user_client):
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


def test_anon_can_view_page(graphql_client):
    page = PageFactory()

    response = graphql_client(
        query="""
            query Page($id: ID!) {
                baPage(id: $id) {
                    pk
                }
            }
        """,
        variables={"id": page.relay_id},
    )

    content = response.json()

    assert content["data"]["baPage"]["pk"] == page.pk


def test_owner_can_view_unpublished_page(django_user_client, graphql_user_client):
    page = PageFactory(user=django_user_client.user, status=Page.PageStatus.DRAFT)

    response = graphql_user_client(
        query="""
            query Page($id: ID!) {
                baPage(id: $id) {
                    pk
                }
            }
        """,
        variables={"id": page.relay_id},
    )

    content = response.json()

    assert content["data"]["baPage"]["pk"] == page.pk


def test_anon_cant_view_unpublished_page(graphql_client):
    page = PageFactory(status=Page.PageStatus.DRAFT)

    response = graphql_client(
        query="""
            query Page($id: ID!) {
                baPage(id: $id) {
                    pk
                }
            }
        """,
        variables={"id": page.relay_id},
    )

    content = response.json()

    assert content["data"]["baPage"] is None


def test_another_user_cant_view_unpublished_page(graphql_user_client):
    page = PageFactory(status=Page.PageStatus.DRAFT)

    response = graphql_user_client(
        query="""
            query Page($id: ID!) {
                baPage(id: $id) {
                    pk
                }
            }
        """,
        variables={"id": page.relay_id},
    )

    content = response.json()

    assert content["data"]["baPage"] is None


def test_anon_cant_view_unpublished_page_by_url(graphql_client):
    page = PageFactory(status=Page.PageStatus.DRAFT)
    url_path = URLPathFactory(target=page, language="en", path="/test-page/", is_active=True)

    response = graphql_client(GET_PAGE_BY_PATH, variables={"path": url_path.path})

    content = response.json()
    assert content["data"]["urlPath"]["target"] is None


def test_user_cant_view_unpublished_page_by_url(graphql_user_client):
    page = PageFactory(status=Page.PageStatus.DRAFT)
    url_path = URLPathFactory(target=page, language="en", path="/test-page/", is_active=True)

    response = graphql_user_client(GET_PAGE_BY_PATH, variables={"path": url_path.path})

    content = response.json()
    assert content["data"]["urlPath"]["target"] is None


def test_owner_can_view_unpublished_page_by_url(django_user_client, graphql_user_client):
    page = PageFactory(user=django_user_client.user, status=Page.PageStatus.DRAFT)
    url_path = URLPathFactory(target=page, language="en", path="/test-page/", is_active=True)

    response = graphql_user_client(GET_PAGE_BY_PATH, variables={"path": url_path.path})

    content = response.json()
    assert content["data"]["urlPath"]["target"]["pk"] == page.pk


def test_owner_can_change_page(django_user_client, graphql_user_client):
    page = PageFactory(
        user=django_user_client.user,
    )

    response = graphql_user_client(
        query=f"""
            query Page($id: ID!) {{
                baPage(id: $id) {{
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

    assert content["data"]["baPage"]["canChange"]
    assert content["data"]["baPage"]["canDelete"]
    assert content["data"]["baPage"]["canChangeFull"]
    assert content["data"]["baPage"]["canDeleteFull"]


def test_another_user_cant_change_page(graphql_user_client):
    page = PageFactory()

    response = graphql_user_client(
        query="""
            query Page($id: ID!) {
                baPage(id: $id) {
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

    assert not content["data"]["baPage"]["canChange"]
    assert not content["data"]["baPage"]["canDelete"]
    assert not content["data"]["baPage"]["canChangeFull"]
    assert not content["data"]["baPage"]["canDeleteFull"]
