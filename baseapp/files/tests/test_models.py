import swapper
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

File = swapper.load_model("baseapp_files", "File")
Comment = swapper.load_model("baseapp_comments", "Comment")


class FileModelTest(TestCase):
    def test_create_file(self):
        File.objects.create()
        self.assertEqual(File.objects.count(), 1)

    def test_comment_files_count(self):
        comment = Comment.objects.create()
        comment_content_type = ContentType.objects.get_for_model(Comment)

        File.objects.create(
            parent_content_type=comment_content_type,
            parent_object_id=comment.pk,
        )

        self.assertEqual(comment.files.count(), 1)
