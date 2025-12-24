from baseapp.content_feed.models import AbstractContentPost, AbstractContentPostImage


class ContentPost(AbstractContentPost):
    class Meta(AbstractContentPost.Meta):
        pass


class ContentPostImage(AbstractContentPostImage):
    class Meta(AbstractContentPostImage.Meta):
        pass
