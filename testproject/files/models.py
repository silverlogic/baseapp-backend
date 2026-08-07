from baseapp.files.models import AbstractFile, AbstractFileTarget


class FileTarget(AbstractFileTarget):
    class Meta(AbstractFileTarget.Meta):
        pass


class File(AbstractFile):
    class Meta(AbstractFile.Meta):
        pass
