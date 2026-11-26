from baseapp_auth.impersonation.models import (
    AbstractImpersonationAction,
    AbstractImpersonationSession,
)


class ImpersonationSession(AbstractImpersonationSession):
    class Meta(AbstractImpersonationSession.Meta):
        pass


class ImpersonationAction(AbstractImpersonationAction):
    class Meta(AbstractImpersonationAction.Meta):
        pass
