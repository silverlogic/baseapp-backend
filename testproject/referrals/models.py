from baseapp_referrals.models import BaseUserReferral


class UserReferral(BaseUserReferral):
    class Meta(BaseUserReferral.Meta):
        pass
