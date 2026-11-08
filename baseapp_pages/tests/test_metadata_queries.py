import pytest
import swapper
from django.contrib.contenttypes.models import ContentType

from baseapp_pages.models import Metadata

from .factories import PageFactory, URLPathFactory

pytestmark = pytest.mark.django_db

Page = swapper.load_model("baseapp_pages", "Page")


def test_page_metadata_row_falls_back_to_title(graphql_client) -> None:
    page = PageFactory(title_en="About")
    Metadata.objects.create(
        target_content_type=ContentType.objects.get_for_model(page),
        target_object_id=page.pk,
        language="en",
        meta_description="About us",
    )

    response = graphql_client(
        query="""
            query Page($id: ID!) {
                page(id: $id) {
                    metadata { metaTitle metaDescription language }
                }
            }
        """,
        variables={"id": page.relay_id},
    )

    assert response.json()["data"]["page"]["metadata"] == {
        "metaTitle": "About",
        "metaDescription": "About us",
        "language": "en",
    }


def test_profile_and_user_metadata(django_user_client, graphql_user_client) -> None:
    user = django_user_client.user

    response = graphql_user_client(
        query="""
            query {
                me {
                    metadata { metaTitle metaDescription metaOgType }
                    profile {
                        metadata {
                            metaTitle
                            metaDescription
                            metaOgType
                            metaOgImage(width: 10, height: 10)
                        }
                    }
                }
            }
        """,
    )

    me = response.json()["data"]["me"]
    assert me["metadata"] == {
        "metaTitle": user.get_full_name(),
        "metaDescription": None,
        "metaOgType": None,
    }
    assert me["profile"]["metadata"] == {
        "metaTitle": user.profile.name,
        "metaDescription": None,
        "metaOgType": "profile",
        "metaOgImage": None,
    }


def test_url_paths_list(graphql_client) -> None:
    page = PageFactory()
    URLPathFactory(target=page, language="en", path="/old/", is_active=False)
    URLPathFactory(target=page, language="en", path="/new/", is_active=True)

    response = graphql_client(
        query="""
            query Page($id: ID!) {
                page(id: $id) {
                    urlPaths { path isActive language }
                }
            }
        """,
        variables={"id": page.relay_id},
    )

    url_paths = response.json()["data"]["page"]["urlPaths"]
    assert sorted(url_paths, key=lambda p: p["path"]) == [
        {"path": "/new/", "isActive": True, "language": "en"},
        {"path": "/old/", "isActive": False, "language": "en"},
    ]


def test_filter_pages_by_status(django_user_client, graphql_user_client) -> None:
    PageFactory(user=django_user_client.user)
    draft = PageFactory(user=django_user_client.user, status=Page.PageStatus.DRAFT)

    response = graphql_user_client(
        query="""
            query {
                allPages(status: DRAFT) {
                    totalCount
                    edges { node { pk status } }
                }
            }
        """,
    )

    all_pages = response.json()["data"]["allPages"]
    assert all_pages["totalCount"] == 1
    assert all_pages["edges"][0]["node"] == {"pk": draft.pk, "status": "DRAFT"}
