import pghistory

from baseapp.maps.models import AbstractGeoJSONFeature


@pghistory.track(
    pghistory.InsertEvent(),
    pghistory.UpdateEvent(),
    pghistory.DeleteEvent(),
    exclude=["modified"],
)
class GeoJSONFeature(AbstractGeoJSONFeature):

    class Meta(AbstractGeoJSONFeature.Meta):
        pass
