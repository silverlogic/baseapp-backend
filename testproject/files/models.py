import swapper

from baseapp.files.models import AbstractFile, AbstractFileTarget


class FileTarget(AbstractFileTarget):
    class Meta(AbstractFileTarget.Meta):
        abstract = False
        swappable = swapper.swappable_setting("baseapp_files", "FileTarget")


class File(AbstractFile):
    class Meta(AbstractFile.Meta):
        abstract = False
        swappable = swapper.swappable_setting("baseapp_files", "File")
