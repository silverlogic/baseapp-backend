from typing import Any


def get_files_interface() -> Any:
    from .interfaces import FilesInterface

    return FilesInterface
