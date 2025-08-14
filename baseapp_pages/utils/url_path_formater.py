import re


class URLPathFormater:
    """
    Ensures the path is valid:
    - Always starts with a single slash
    - Never ends with a slash (unless it's just '/')
    - Never has double slashes
    - Is at least '/'
    Raises ValueError if the format is not compatible.
    """

    path: str

    def __init__(self, path: str):
        self.path = path

    def __call__(self) -> str:
        return self.format()

    def format(self) -> str:
        self._clean_path()
        self._replace_multiple_slashes()
        self._ensure_starts_with_slash()
        self._remove_trailing_slash()
        self._validate_path()

        return self.path

    def _clean_path(self) -> str:
        self.path = self.path.strip()
        if not self.path:
            raise ValueError("Path cannot be empty.")

    def _replace_multiple_slashes(self) -> str:
        self.path = re.sub(r"/+", "/", self.path)

    def _ensure_starts_with_slash(self) -> str:
        if not self.path.startswith("/"):
            self.path = "/" + self.path

    def _remove_trailing_slash(self) -> str:
        if len(self.path) > 1 and self.path.endswith("/"):
            self.path = self.path[:-1]

    def _validate_path(self) -> str:
        if not self.path.startswith("/"):
            raise ValueError("Path must start with a slash ('/').")
        if "//" in self.path:
            raise ValueError("Path must not contain double slashes ('//').")
        if len(self.path) > 1 and self.path.endswith("/"):
            raise ValueError("Path must not end with a slash unless it is root ('/').")
