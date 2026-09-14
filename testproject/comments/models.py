from baseapp_comments.models import AbstractComment, AbstractCommentableMetadata


class Comment(AbstractComment):
    class Meta(AbstractComment.Meta):
        pass


class CommentableMetadata(AbstractCommentableMetadata):
    class Meta(AbstractCommentableMetadata.Meta):
        pass
