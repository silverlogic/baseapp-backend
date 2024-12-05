import pghistory
from baseapp_comments.models import AbstractComment


@pghistory.track(
    pghistory.InsertEvent(),
    pghistory.UpdateEvent(),
    pghistory.DeleteEvent(),
    exclude=["comments_count", "reactions_count", "modified"],
)
class Comment(AbstractComment):

    class Meta(AbstractComment.Meta):
        pass
