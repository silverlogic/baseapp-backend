from baseapp.geo.models import AbstractGeoJSONFeature


class GeoJSONFeature(AbstractGeoJSONFeature):
    class Meta(AbstractGeoJSONFeature.Meta):
        pass
