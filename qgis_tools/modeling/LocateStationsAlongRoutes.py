from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessing,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterDistance,
    QgsProcessingParameterFeatureSink,
    QgsFeatureSink,
    QgsFeature,
    QgsFields,
    QgsField,
    QgsSpatialIndex,
)
from qgis.PyQt.QtCore import QMetaType


class LocateStationsAlongRoutes(QgsProcessingAlgorithm):
    STATIONS       = "STATIONS"
    NAME_FIELD     = "NAME_FIELD"
    ROUTES         = "ROUTES"
    ROUTES_RID     = "ROUTES_RID"
    DISTANCE       = "DISTANCE"
    OUTPUT         = "OUTPUT"

    def name(self):
        return "locate_stations_along_routes"

    def displayName(self):
        return "Locate stations along routes"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Modeling"

    def groupId(self):
        return "concordiariverlab_floodtools_modeling"

    def createInstance(self):
        return LocateStationsAlongRoutes()

    def shortHelpString(self):
        return (
            "Locate stations along routes\n\n"
            "Snaps gauging station points to the nearest D8 route within a search "
            "radius, and computes RID and MEAS (linear distance along the matched "
            "reach) for each. Mirrors ArcGIS Locate Features Along Routes.\n\n"
            "Use this to locate flood discharge gauging stations on the D8 network "
            "when they differ from the stations used for LiDAR discharges (if they "
            "are the same stations, reuse the RID/MEAS already computed during the "
            "LiDAR discharge step instead of re-running this).\n\n"
            "Inputs:\n"
            "- Stations: gauging station points\n"
            "- Name field: station name field (must match discharge CSV headers)\n"
            "- Routes D8: watershed-scale D8 route network (lines)\n"
            "- RID field in routes: unique reach ID field\n"
            "- Search radius: maximum snap distance (e.g. 10000)\n\n"
            "Output: stations with RID and MEAS fields added; stations farther than "
            "the search radius from any route are dropped and logged as warnings.\n"
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.STATIONS, "Stations", [QgsProcessing.TypeVectorPoint],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.NAME_FIELD, "Name field", parentLayerParameterName=self.STATIONS,
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.ROUTES, "Routes D8 (lines)", [QgsProcessing.TypeVectorLine],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.ROUTES_RID, "RID field in routes", parentLayerParameterName=self.ROUTES,
        ))
        self.addParameter(QgsProcessingParameterDistance(
            self.DISTANCE, "Search radius", defaultValue=10000.0,
            parentParameterName=self.ROUTES,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, "Stations with RID/MEAS",
        ))

    def processAlgorithm(self, parameters, context, feedback):
        stations       = self.parameterAsSource(parameters, self.STATIONS, context)
        name_field     = self.parameterAsString(parameters, self.NAME_FIELD, context)
        routes         = self.parameterAsVectorLayer(parameters, self.ROUTES, context)
        rid_field      = self.parameterAsString(parameters, self.ROUTES_RID, context)
        distance       = self.parameterAsDouble(parameters, self.DISTANCE, context)

        if stations is None:
            raise QgsProcessingException("Stations layer is invalid")
        if routes is None:
            raise QgsProcessingException("Routes layer is invalid")

        located = locate_stations_along_routes(
            stations=stations,
            name_field=name_field,
            routes=routes,
            rid_field=rid_field,
            distance=distance,
            feedback=feedback,
        )

        out_fields = QgsFields(stations.fields())
        out_fields.append(QgsField("RID", QMetaType.LongLong))
        out_fields.append(QgsField("MEAS", QMetaType.Double))

        sink, dest_id = self.parameterAsSink(
            parameters, self.OUTPUT, context,
            out_fields, stations.wkbType(), stations.sourceCrs(),
        )
        if sink is None:
            raise QgsProcessingException("Could not create output sink")

        for f in located:
            if feedback.isCanceled():
                break
            sink.addFeature(f, QgsFeatureSink.FastInsert)

        return {self.OUTPUT: dest_id}


# =============================================================================
# Core function — extracted from spatialize_q_from_gauging_stations Step 3
# =============================================================================

def locate_stations_along_routes(
    stations,
    name_field,
    routes,
    rid_field,
    distance,
    feedback=None,
):
    """
    Snaps each station to the nearest route within `distance`, and computes
    RID (matched reach ID) and MEAS (linear distance along that reach).


    Mirrors ArcGIS Locate Features Along Routes, and the same logic
    previously embedded as Step 3 of spatialize_q_from_gauging_stations —
    pulled out here so it can be reused independently for flood discharge
    gauging stations that differ from the LiDAR discharge stations.

    Args:
        stations       : QgsFeatureSource (points) — gauging stations
        name_field     : str — station name field (must match CSV headers)
        routes         : QgsVectorLayer (lines) — D8 route network
        rid_field      : str — RID field in routes
        distance       : float — maximum snap distance in CRS units
        feedback       : QgsProcessingFeedback or None

    Returns:
        list of QgsFeature (with geometry) — fields: all input station fields, name, RID, MEAS
    """
    def info(msg):
        if feedback:
            feedback.pushInfo(msg)

    def warn(msg):
        if feedback:
            feedback.pushWarning(msg)

    info("Building route spatial index…")
    route_index = QgsSpatialIndex()
    route_feats = {}
    for feat in routes.getFeatures():
        route_index.insertFeature(feat)
        route_feats[feat.id()] = feat

    out_fields = QgsFields(stations.fields())
    out_fields.append(QgsField("RID", QMetaType.LongLong))
    out_fields.append(QgsField("MEAS", QMetaType.Double))

    located = []
    skipped = 0

    for feat in stations.getFeatures():
        if feedback and feedback.isCanceled():
            break

        pt_geom = feat.geometry()
        if pt_geom is None or pt_geom.isEmpty():
            continue

        search_rect = pt_geom.boundingBox()
        search_rect.grow(distance)
        candidate_ids = route_index.intersects(search_rect)

        best_rid  = None
        best_meas = None
        best_dist = float("inf")

        for fid in candidate_ids:
            route_feat = route_feats[fid]
            route_geom = route_feat.geometry()
            nearest    = route_geom.nearestPoint(pt_geom)
            snap_dist  = nearest.distance(pt_geom)

            if snap_dist <= distance and snap_dist < best_dist:
                best_dist = snap_dist
                best_rid  = int(route_feat[rid_field])
                best_meas = route_geom.lineLocatePoint(pt_geom)

        if best_rid is None:
            skipped += 1
            warn(
                f"  Station '{feat[name_field]}' is more than {distance}m "
                f"from any route — skipping."
            )
            continue

        out_feat = QgsFeature(out_fields)
        out_feat.setGeometry(pt_geom)
        out_feat.setAttributes(feat.attributes() + [best_rid, best_meas])
        located.append(out_feat)

    info(f"Located {len(located)} station(s) on the route network "
         f"({skipped} skipped, beyond search radius).")

    return located