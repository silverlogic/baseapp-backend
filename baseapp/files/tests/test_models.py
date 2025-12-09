import swapper
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import TestCase

from baseapp.files.utils import (
    default_files_count,
    get_or_create_file_target,
    recalculate_files_count,
    set_files_parent,
)

File = swapper.load_model("baseapp_files", "File")
FileTarget = swapper.load_model("baseapp_files", "FileTarget")
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


class FileTargetTest(TestCase):
    def test_file_target_creation(self):
        comment = Comment.objects.create()
        file_target = comment.get_file_target()

        self.assertIsNotNone(file_target)
        self.assertEqual(file_target.target_object_id, comment.pk)
        self.assertTrue(file_target.is_files_enabled)
        self.assertEqual(file_target.files_count, {"total": 0})

    def test_file_target_str_method(self):
        comment = Comment.objects.create()
        file_target = comment.get_file_target()

        expected_str = f"FileTarget for {file_target.target_content_type} #{comment.pk}"
        self.assertEqual(str(file_target), expected_str)

    def test_file_target_unique_constraint(self):
        comment = Comment.objects.create()
        comment_content_type = ContentType.objects.get_for_model(Comment)

        FileTarget.objects.create(
            target_content_type=comment_content_type,
            target_object_id=comment.pk,
        )

        file_target2, created = FileTarget.objects.get_or_create(
            target_content_type=comment_content_type,
            target_object_id=comment.pk,
        )

        self.assertFalse(created)
        self.assertEqual(FileTarget.objects.count(), 1)

    def test_file_target_files_count_update_single_type(self):
        comment = Comment.objects.create()
        comment_content_type = ContentType.objects.get_for_model(Comment)

        File.objects.create(
            parent_content_type=comment_content_type,
            parent_object_id=comment.pk,
            file_content_type="image/png",
        )

        file_target = comment.get_file_target()
        self.assertEqual(file_target.files_count["total"], 1)
        self.assertEqual(file_target.files_count.get("image/png"), 1)

    def test_file_target_files_count_update_multiple_types(self):
        comment = Comment.objects.create()
        comment_content_type = ContentType.objects.get_for_model(Comment)

        File.objects.create(
            parent_content_type=comment_content_type,
            parent_object_id=comment.pk,
            file_content_type="image/png",
        )
        File.objects.create(
            parent_content_type=comment_content_type,
            parent_object_id=comment.pk,
            file_content_type="image/jpeg",
        )
        File.objects.create(
            parent_content_type=comment_content_type,
            parent_object_id=comment.pk,
            file_content_type="image/png",
        )

        file_target = comment.get_file_target()
        self.assertEqual(file_target.files_count["total"], 3)
        self.assertEqual(file_target.files_count.get("image/png"), 2)
        self.assertEqual(file_target.files_count.get("image/jpeg"), 1)

    def test_file_target_is_files_enabled_can_be_disabled(self):
        comment = Comment.objects.create()
        file_target = comment.get_file_target()

        file_target.is_files_enabled = False
        file_target.save()

        self.assertFalse(comment.is_files_enabled)

    def test_cannot_attach_file_when_files_disabled(self):
        comment = Comment.objects.create()
        comment_content_type = ContentType.objects.get_for_model(Comment)

        # Create FileTarget with is_files_enabled=False
        file_target = comment.get_file_target()
        file_target.is_files_enabled = False
        file_target.save()

        # Try to create a file for this comment
        with self.assertRaises(ValidationError) as cm:
            File.objects.create(
                parent_content_type=comment_content_type,
                parent_object_id=comment.pk,
                file_content_type="image/png",
            )

        self.assertEqual(cm.exception.code, "files_disabled")
        self.assertIn("Files are not enabled", str(cm.exception))

    def test_can_attach_file_when_files_enabled(self):
        comment = Comment.objects.create()
        comment_content_type = ContentType.objects.get_for_model(Comment)

        # Create FileTarget with is_files_enabled=True (default)
        file_target = comment.get_file_target()
        self.assertTrue(file_target.is_files_enabled)

        # This should work without raising an error
        file_obj = File.objects.create(
            parent_content_type=comment_content_type,
            parent_object_id=comment.pk,
            file_content_type="image/png",
        )

        self.assertIsNotNone(file_obj.pk)
        self.assertEqual(file_obj.parent_object_id, comment.pk)

    def test_fileable_model_properties(self):
        comment = Comment.objects.create()

        self.assertTrue(comment.is_files_enabled)
        self.assertEqual(comment.files_count, {"total": 0})

    def test_fileable_model_properties_multiple_accesses(self):
        comment = Comment.objects.create()

        files_count_1 = comment.files_count
        files_count_2 = comment.files_count

        self.assertEqual(files_count_1, files_count_2)
        self.assertEqual(FileTarget.objects.count(), 1)


class FileUtilsTest(TestCase):
    def test_default_files_count(self):
        result = default_files_count()
        self.assertEqual(result, {"total": 0})

    def test_get_or_create_file_target_creates_new(self):
        comment = Comment.objects.create()

        initial_count = FileTarget.objects.count()
        file_target = get_or_create_file_target(comment)

        self.assertEqual(FileTarget.objects.count(), initial_count + 1)
        self.assertEqual(file_target.target_object_id, comment.pk)

    def test_get_or_create_file_target_gets_existing(self):
        comment = Comment.objects.create()

        file_target1 = get_or_create_file_target(comment)
        file_target2 = get_or_create_file_target(comment)

        self.assertEqual(file_target1.pk, file_target2.pk)
        self.assertEqual(FileTarget.objects.count(), 1)

    def test_recalculate_files_count_with_none(self):
        recalculate_files_count(None)

    def test_recalculate_files_count_empty(self):
        comment = Comment.objects.create()
        recalculate_files_count(comment)

        file_target = comment.get_file_target()
        self.assertEqual(file_target.files_count, {"total": 0})

    def test_recalculate_files_count_with_files(self):
        comment = Comment.objects.create()
        comment_content_type = ContentType.objects.get_for_model(Comment)

        File.objects.create(
            parent_content_type=comment_content_type,
            parent_object_id=comment.pk,
            file_content_type="image/png",
        )

        recalculate_files_count(comment)

        file_target = comment.get_file_target()
        self.assertEqual(file_target.files_count["total"], 1)

    def test_set_files_parent_with_empty_list(self):
        comment = Comment.objects.create()
        set_files_parent(comment, [])

    def test_set_files_parent_with_none(self):
        comment = Comment.objects.create()
        set_files_parent(comment, None)

    def test_set_files_parent_moves_file(self):
        comment1 = Comment.objects.create()
        comment2 = Comment.objects.create()
        comment1_content_type = ContentType.objects.get_for_model(Comment)

        file_obj = File.objects.create(
            parent_content_type=comment1_content_type,
            parent_object_id=comment1.pk,
            file_content_type="image/png",
        )

        set_files_parent(comment2, [file_obj])

        file_obj.refresh_from_db()
        self.assertEqual(file_obj.parent_object_id, comment2.pk)

        file_target1 = comment1.get_file_target()
        file_target2 = comment2.get_file_target()
        self.assertEqual(file_target1.files_count["total"], 0)
        self.assertEqual(file_target2.files_count["total"], 1)

    def test_set_files_parent_same_parent(self):
        comment = Comment.objects.create()
        comment_content_type = ContentType.objects.get_for_model(Comment)

        file_obj = File.objects.create(
            parent_content_type=comment_content_type,
            parent_object_id=comment.pk,
        )

        set_files_parent(comment, [file_obj])

        file_obj.refresh_from_db()
        self.assertEqual(file_obj.parent_object_id, comment.pk)


class FileTargetSignalsTest(TestCase):
    def test_file_creation_updates_file_target(self):
        comment = Comment.objects.create()
        comment_content_type = ContentType.objects.get_for_model(Comment)

        File.objects.create(
            parent_content_type=comment_content_type,
            parent_object_id=comment.pk,
            file_content_type="image/png",
        )

        file_target = FileTarget.objects.get(
            target_content_type=comment_content_type,
            target_object_id=comment.pk,
        )
        self.assertEqual(file_target.files_count["total"], 1)

    def test_file_deletion_updates_file_target(self):
        comment = Comment.objects.create()
        comment_content_type = ContentType.objects.get_for_model(Comment)

        file_obj = File.objects.create(
            parent_content_type=comment_content_type,
            parent_object_id=comment.pk,
            file_content_type="image/png",
        )

        file_obj.delete()

        file_target = FileTarget.objects.get(
            target_content_type=comment_content_type,
            target_object_id=comment.pk,
        )
        self.assertEqual(file_target.files_count["total"], 0)
