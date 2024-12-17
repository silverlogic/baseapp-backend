import pghistory
from baseapp_profiles.models import AbstractProfile


@pghistory.track(
    pghistory.InsertEvent(),
    pghistory.UpdateEvent(),
    pghistory.DeleteEvent(),
)
class Profile(AbstractProfile):
    class Meta(AbstractProfile.Meta):
        pass
