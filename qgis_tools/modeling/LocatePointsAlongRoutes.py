from pathlib import Path
import sys

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsFeatureSink,
    QgsFeature,
    QgsFields,
    QgsField,
    QgsWkbTypes,
    QgsGeometry,
    QgsPointXY,
    QgsSpatialIndex,
)
from qgis.PyQt.QtCore import QMetaType

sys.path.append(str(Path(__file__).resolve().parents[1]))


class LocatePointsAlongRoutes(QgsProcessingAlgorithm):
    POINTS          = "POINTS"
    POINTS_RID_FIELD = "POINTS_RID_FIELD"
    ROUTES          = "ROUTES"
    ROUTES_RID_FIELD = "ROUTES_RID_FIELD"
    DISTANCE        = "DISTANCE"
    OUTPUT          = "OUTPUT"

    def name(self):
        return "locate_points_along_routes"

    def displayName(self):
        return "Locate points along routes"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Modeling"

    def groupId(self):
        return "concordiariverlab_floodtools_modeling"

    def createInstance(self):
        return LocatePointsAlongRoutes()

    def shortHelpString(self):
        return (
            "Locate points along routes\n\n"
            "Locates points along a route network by computing the linear "
            "distance (MEAS) of each point along its corresponding reach. "
            "Points are matched to reaches by RID field.\n\n"
            "Inputs:\n"
            "- Points layer\n"
            "- RID field in the points layer\n"
            "- Routes layer (lines)\n"
            "- RID field in the routes layer\n"
            "- Maximum snap distance (e.g. 10000)\n\n"
            "Output:\n"
            "- Table with RID and MEAS fields\n"
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessing,
            QgsProcessingParameterVectorLayer,
            QgsProcessingParameterFeatureSource,
            QgsProcessingParameterField,
            QgsProcessingParameterDistance,
            QgsProcessingParameterFeatureSink,
        )

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.POINTS,
                "Points layer",
                [QgsProcessing.TypeVectorPoint],
            )
        )

        self.addParameter(
            QgsProcessingParameterField(
                self.POINTS_RID_FIELD,
                "RID field in the points layer",
                parentLayerParameterName=self.POINTS,
            )
        )

        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.ROUTES,
                "Routes layer (lines)",
                [QgsProcessing.TypeVectorLine],
            )
        )

        self.addParameter(
            QgsProcessingParameterField(
                self.ROUTES_RID_FIELD,
                "RID field in the routes layer",
                parentLayerParameterName=self.ROUTES,
            )
        )

        self.addParameter(
            QgsProcessingParameterDistance(
                self.DISTANCE,
                "Maximum snap distance",
                defaultValue=10000.0,
                parentParameterName=self.ROUTES,
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                "Output table",
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        points           = self.parameterAsSource(parameters, self.POINTS, context)
        points_rid_field = self.parameterAsString(parameters, self.POINTS_RID_FIELD, context)
        routes           = self.parameterAsVectorLayer(parameters, self.ROUTES, context)
        routes_rid_field = self.parameterAsString(parameters, self.ROUTES_RID_FIELD, context)
        distance         = self.parameterAsDouble(parameters, self.DISTANCE, context)

        if points is None:
            raise QgsProcessingException("Points layer is invalid")
        if routes is None:
            raise QgsProcessingException("Routes layer is invalid")

        out_features = locate_points_along_routes(
            points=points,
            points_rid_field=points_rid_field,
            routes=routes,
            routes_rid_field=routes_rid_field,
            distance=distance,
            feedback=feedback,
        )

        out_fields = QgsFields()
        out_fields.append(QgsField("id",   QMetaType.LongLong))
        out_fields.append(QgsField("RID",  QMetaType.LongLong))
        out_fields.append(QgsField("MEAS", QMetaType.Double))

        (sink, sink_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            out_fields,
            QgsWkbTypes.NoGeometry,
            routes.sourceCrs(),
        )

        for f in out_features:
            if feedback.isCanceled():
                break
            sink.addFeature(f, QgsFeatureSink.FastInsert)

        return {self.OUTPUT: sink_id}


# =============================================================================
# Core function
# =============================================================================

def locate_points_along_routes(
    points,
    points_rid_field,
    routes,
    routes_rid_field,
    distance=10000.0,
    feedback=None,
):
    """
    For each point, compute its linear distance (MEAS) along the reach
    identified by its RID field, using QgsGeometry.lineLocatePoint().

    Points are matched to reaches by RID. Only points within the snap
    distance of their matched reach are included in the output.

    Mirrors ArcGIS execute_LocatePointsAlongRoutes() from
    LocatePointsAlongRoutes.py.

    Args:
        points           : QgsFeatureSource (points) — e.g. QpointsD8
        points_rid_field : str — RID field in points layer
        routes           : QgsVectorLayer (lines) — e.g. routes_main
        routes_rid_field : str — RID field in routes layer
        distance         : float — maximum snap distance in CRS units
        feedback         : QgsProcessingFeedback or None

    Returns:
        list of QgsFeature (no geometry) with fields: id, RID, MEAS
    """
    if feedback:
        feedback.pushInfo("Building route index for point location…")

    # Index routes by RID
    routes_by_rid = {}
    for f in routes.getFeatures():
        rid = f[routes_rid_field]
        if rid is None:
            continue
        routes_by_rid[int(rid)] = f

    # Group points by RID
    points_by_rid = {}
    for f in points.getFeatures():
        rid = f[points_rid_field]
        if rid is None:
            continue
        rid = int(rid)
        if rid not in points_by_rid:
            points_by_rid[rid] = []
        points_by_rid[rid].append(f)

    if feedback:
        feedback.pushInfo(
            f"Locating points along {len(routes_by_rid)} reach(es)…"
        )

    out_fields = QgsFields()
    out_fields.append(QgsField("id",   QMetaType.LongLong))
    out_fields.append(QgsField("RID",  QMetaType.LongLong))
    out_fields.append(QgsField("MEAS", QMetaType.Double))

    out_features = []
    total = len(routes_by_rid)

    for i, (rid, route_feat) in enumerate(routes_by_rid.items()):
        if feedback and feedback.isCanceled():
            break
        if feedback and total:
            feedback.setProgress(int(100 * i / max(1, total)))

        route_geom = route_feat.geometry()
        if route_geom is None or route_geom.isEmpty():
            continue

        pts = points_by_rid.get(rid, [])
        if not pts:
            continue

        for pt_feat in pts:
            pt_geom = pt_feat.geometry()
            if pt_geom is None or pt_geom.isEmpty():
                continue

            # Check snap distance
            nearest_pt = route_geom.nearestPoint(pt_geom)
            snap_dist  = nearest_pt.distance(pt_geom)
            if snap_dist > distance:
                continue

            # Compute linear distance along route
            meas = route_geom.lineLocatePoint(pt_geom)

            pt_id = pt_feat["id"] if "id" in [
                f.name() for f in pt_feat.fields()
            ] else pt_feat.id()

            f = QgsFeature(out_fields)
            f.setAttributes([int(pt_id), int(rid), float(meas)])
            out_features.append(f)

    if feedback:
        feedback.pushInfo(
            f"Located {len(out_features)} point(s) along routes."
        )

    return out_features