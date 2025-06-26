class BaseAppBackendPDFException(Exception):
    pass


class BaseAppBackendPDFChromeNotInstalledException(BaseAppBackendPDFException):
    def __init__(self, *args, **kwargs):
        super().__init__("google-chrome is not installed")


class BaseAppBackendPDFRenderToPDFException(BaseAppBackendPDFException):
    pass
