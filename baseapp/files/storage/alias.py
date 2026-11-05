from datetime import datetime
from typing import IO, Any

from django.core.files.storage import Storage, storages
from django.utils.deconstruct import deconstructible


@deconstructible
class AliasStorage(Storage):
    """
    A storage that stands for a ``STORAGES`` alias and resolves it on every operation.

    Use it on model fields whose storage differs per environment (a private S3 bucket in
    production, a local directory in development) without binding the field to one backend:
    migrations record ``AliasStorage("private")`` instead of the backend's class and options,
    and ``override_settings(STORAGES=...)`` in tests takes effect immediately.

        file = models.FileField(storage=AliasStorage("private"))
    """

    def __init__(self, alias: str = "default") -> None:
        self.alias = alias

    @property
    def backend(self) -> Storage:
        """The storage the alias currently names."""
        return storages[self.alias]

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, AliasStorage) and other.alias == self.alias

    def __hash__(self) -> int:
        return hash((AliasStorage, self.alias))

    def __repr__(self) -> str:
        return f"AliasStorage({self.alias!r})"

    # Naming is delegated as a whole, so the backend's own rules (e.g. S3 overwrites) apply.
    def generate_filename(self, filename: str) -> str:
        return self.backend.generate_filename(filename)

    def get_valid_name(self, name: str) -> str:
        return self.backend.get_valid_name(name)

    def get_available_name(self, name: str, max_length: int | None = None) -> str:
        return self.backend.get_available_name(name, max_length=max_length)

    def get_alternative_name(self, file_root: str, file_ext: str) -> str:
        return self.backend.get_alternative_name(file_root, file_ext)

    def open(self, name: str, mode: str = "rb") -> IO[Any]:
        return self.backend.open(name, mode)

    def save(self, name: str | None, content: Any, max_length: int | None = None) -> str:
        return self.backend.save(name, content, max_length=max_length)

    def delete(self, name: str) -> None:
        self.backend.delete(name)

    def exists(self, name: str) -> bool:
        return self.backend.exists(name)

    def listdir(self, path: str) -> tuple[list[str], list[str]]:
        return self.backend.listdir(path)

    def path(self, name: str) -> str:
        return self.backend.path(name)

    def size(self, name: str) -> int:
        return self.backend.size(name)

    def url(self, name: str | None, *args: Any, **kwargs: Any) -> str:
        return self.backend.url(name, *args, **kwargs)

    def get_accessed_time(self, name: str) -> datetime:
        return self.backend.get_accessed_time(name)

    def get_created_time(self, name: str) -> datetime:
        return self.backend.get_created_time(name)

    def get_modified_time(self, name: str) -> datetime:
        return self.backend.get_modified_time(name)
