import swapper
from django.utils.translation import gettext_lazy as _
from graphene_django.filter import DjangoFilterConnectionField

from baseapp_core.graphql import Node, get_object_type_for_model

from .filters import GeoJSONFeatureFilter

GeoJSONFeature = swapper.load_model("baseapp_geo", "GeoJSONFeature")


class GeoQueries:
    geo_feature = Node.Field(get_object_type_for_model(GeoJSONFeature))
    geo_features = DjangoFilterConnectionField(
        get_object_type_for_model(GeoJSONFeature),
        filterset_class=GeoJSONFeatureFilter,
        max_limit=100,
        description=_(
            "List GeoJSON features for map display. Supports bbox and near "
            "(lng,lat,radius-in-meters) filters."
        ),
    )
