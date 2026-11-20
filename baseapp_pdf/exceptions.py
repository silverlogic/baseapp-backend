class BaseAppBackendPDFException(Exception):
    pass


class BaseAppBackendPDFChromeNotInstalledException(BaseAppBackendPDFException):
    def __init__(self, binary: str = "google-chrome", *args, **kwargs) -> None:
        super().__init__(f"{binary} is not installed")


class BaseAppBackendPDFRenderToPDFException(BaseAppBackendPDFException):
    pass
