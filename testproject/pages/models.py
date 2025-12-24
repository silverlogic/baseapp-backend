import pghistory

from baseapp_pages.models import AbstractPage


@pghistory.track(
    pghistory.InsertEvent(),
    pghistory.UpdateEvent(),
    pghistory.DeleteEvent(),
)
class Page(AbstractPage):
    class Meta(AbstractPage.Meta):
        db_table = "baseapp_pages_page"

    @classmethod
    def get_graphql_object_type(cls):
        from baseapp_pages.graphql.object_types import PageObjectType

        return PageObjectType
