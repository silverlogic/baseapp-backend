from baseapp_comments.models import AbstractComment


class Comment(AbstractComment):
    class Meta(AbstractComment.Meta):
        pass
