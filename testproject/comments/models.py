from baseapp_comments.models import AbstractComment, AbstractCommentStats  # noqa


class Comment(AbstractComment):
    class Meta(AbstractComment.Meta):
        pass


class CommentStats(AbstractCommentStats):
    class Meta(AbstractCommentStats.Meta):
        pass
