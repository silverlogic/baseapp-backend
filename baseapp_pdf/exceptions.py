class BaseAppBackendPDFException(Exception):
    pass


class BaseAppBackendPDFChromeNotInstalledException(BaseAppBackendPDFException):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__("google-chrome is not installed")


class BaseAppBackendPDFRenderToPDFException(BaseAppBackendPDFException):
    pass
