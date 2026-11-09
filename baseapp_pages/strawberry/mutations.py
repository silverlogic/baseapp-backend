import strawberry
import swapper
from django.utils.translation import gettext_lazy as _
from strawberry import UNSET
from strawberry.types import Info

from baseapp_core.graphql import get_pk_from_relay_id
from baseapp_core.strawberry import RelayMutationInput, RelayMutationPayload
from baseapp_core.strawberry.connections import Edge
from baseapp_core.strawberry.mutations import (
    add_request_files,
    delete_node_mutation,
    input_data,
    relay_mutation,
    serializer_errors,
)

from ..serializers import PageSerializer
from .types import PageLazyType

Page = swapper.load_model("baseapp_pages", "Page")
page_app_label = Page._meta.app_label


@strawberry.input(name="PageCreateInput")
class PageCreateInput(RelayMutationInput):
    user: str | None = UNSET
    title: str | None = UNSET
    body: str | None = UNSET
    url_path: str | None = UNSET


@strawberry.type(name="PageCreatePayload")
class PageCreatePayload(RelayMutationPayload):
    page: Edge[PageLazyType] | None = None


@strawberry.input(name="PageEditInput")
class PageEditInput(RelayMutationInput):
    id: strawberry.ID
    user: str | None = UNSET
    title: str | None = UNSET
    body: str | None = UNSET
    url_path: str | None = UNSET


@strawberry.type(name="PageEditPayload")
class PageEditPayload(RelayMutationPayload):
    page: PageLazyType | None = None


@strawberry.type
class PagesMutations:
    @relay_mutation(login_required=True)
    def page_create(self, info: Info, input: PageCreateInput) -> PageCreatePayload | None:
        if not info.context.user.has_perm(f"{page_app_label}.add_page"):
            raise PermissionError(_("You don't have permission to create a page"))

        data = add_request_files(info, input_data(input))
        serializer = PageSerializer(data=data, context={"request": info.context})
        if not serializer.is_valid():
            return PageCreatePayload(errors=serializer_errors(serializer))
        return PageCreatePayload(page=Edge(node=serializer.save(), cursor=None))

    @relay_mutation(login_required=True)
    def page_edit(self, info: Info, input: PageEditInput) -> PageEditPayload | None:
        instance = Page.objects.get(pk=get_pk_from_relay_id(input.id))
        if not info.context.user.has_perm(f"{page_app_label}.change_page", instance):
            raise PermissionError(_("You don't have permission to edit this page"))

        serializer = PageSerializer(
            instance=instance,
            data=input_data(input),
            partial=True,
            context={"request": info.context},
        )
        if not serializer.is_valid():
            return PageEditPayload(errors=serializer_errors(serializer))
        return PageEditPayload(page=serializer.save())

    page_delete = delete_node_mutation()
