from django.test import TestCase
import swapper

File = swapper.load_model("baseapp_files", "File")


class FileModelTest(TestCase):
    def test_create_file(self):
        File.objects.create()
        self.assertEqual(File.objects.count(), 1)
