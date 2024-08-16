from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("baseapp_backend")
except PackageNotFoundError:
    __version__ = None
