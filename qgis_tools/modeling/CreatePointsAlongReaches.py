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
)
from qgis.PyQt.QtCore import QMetaType

sys.path.append(str(Path(__file__).resolve().parents[1]))
from tree_qgis.TreeTools import place_points_at_regular_interval


class CreatePointsAlongReaches(QgsProcessingAlgorithm):
    ROUTES = "ROUTES"
    LINKS = "LINKS"
    RID_FIELD = "RID_FIELD"
    INTERVAL = "INTERVAL"
    OUTPUT = "OUTPUT"

    def name(self):
        return "create_points_along_route_feature_class"

    def displayName(self):
        return "Create points along route feature class"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Modeling"

    def groupId(self):
        return "concordiariverlab_floodtools_modeling"

    def createInstance(self):
        return CreatePointsAlongReaches()

    def shortHelpString(self):
        return (
            "Create points along route feature class\n\n"
            "Creates points placed at a regular interval along each reach in the network, "
            "ordered downstream to upstream. Uses M-values from the routes to interpolate "
            "point locations. Used as input to the Extract Water Surface tool.\n\n"
            "Inputs:\n"
            "- Route feature class: oriented route network with M-values (routes_main)\n"
            "- Route links table: DownID/UpID link table (routes_main_links)\n"
            "- RouteID field: RID\n"
            "- Interval: distance between points in metres (default 5m)\n\n"
            "Output:\n"
            "- target_pts: point feature layer with fields id, RID, MEAS\n"
            "  After running, manually delete points outside the DEM and under bridges.\n"
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessing,
            QgsProcessingParameterVectorLayer,
            QgsProcessingParameterField,
            QgsProcessingParameterNumber,
            QgsProcessingParameterFeatureSink,
        )

        self.addParameter(QgsProcessingParameterVectorLayer(
            self.ROUTES,
            "Route feature class (routes_main)",
            [QgsProcessing.TypeVectorLine],
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.LINKS,
            "Route links table (routes_main_links)",
            [QgsProcessing.TypeVector],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.RID_FIELD,
            "RouteID field",
            parentLayerParameterName=self.ROUTES,
            defaultValue="RID",
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.INTERVAL,
            "Interval between points (metres)",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=5.0,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT,
            "target_pts",
        ))


    def processAlgorithm(self, parameters, context, feedback):
        routes = self.parameterAsVectorLayer(parameters, self.ROUTES, context)
        links = self.parameterAsVectorLayer(parameters, self.LINKS, context)
        rid_field = self.parameterAsString(parameters, self.RID_FIELD, context)
        interval = self.parameterAsDouble(parameters, self.INTERVAL, context)

        if routes is None:
            raise QgsProcessingException("Routes layer is invalid")
        if links is None:
            raise QgsProcessingException("Links layer is invalid")

        rows = place_points_at_regular_interval(
            routes=routes,
            links=links,
            rid_field=rid_field,
            interval=interval,
            feedback=feedback,
        )

        # Build output fields
        out_fields = QgsFields()
        out_fields.append(QgsField("id", QMetaType.LongLong))
        out_fields.append(QgsField("RID", QMetaType.LongLong))
        out_fields.append(QgsField("MEAS", QMetaType.Double))

        # Build geometry lookup with M-values
        reach_geoms_m = {}
        for feat in routes.getFeatures():
            rid = int(feat[rid_field])
            geom = feat.geometry()
            # Extract vertices with M-values
            line_m = []
            for v_idx in range(geom.constGet().numPoints()):
                pt = geom.constGet().pointN(v_idx)
                line_m.append(pt)
            reach_geoms_m[rid] = line_m

        (sink, sink_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context,
            out_fields,
            QgsWkbTypes.Point,
            routes.sourceCrs(),
        )

        for pt_id, rid, meas in rows:
            if feedback.isCanceled():
                break
            line_m = reach_geoms_m.get(rid)
            if line_m is None:
                continue

            # Interpolate point at M-value
            pt_xy = _interpolate_point_on_line(line_m, meas)
            if pt_xy is None:
                continue

            f = QgsFeature(out_fields)
            f.setGeometry(QgsGeometry.fromPointXY(pt_xy))
            f.setAttributes([pt_id, rid, meas])
            sink.addFeature(f, QgsFeatureSink.FastInsert)

        return {self.OUTPUT: sink_id}


# =============================================================================
# Helpers
# =============================================================================

def _interpolate_point_on_line(line_m, target_m):
    """
    Interpolates XY coordinates at a target M-value along a polyline with M-values.

    Args:
        line_m: list of QgsPoint objects with m() values
        target_m: float - target M-value to interpolate at

    Returns:
        QgsPointXY at interpolated location, or None if out of range
    """
    if not line_m or len(line_m) < 2:
        return None

    # Find the segment containing target_m
    for i in range(len(line_m) - 1):
        m0 = line_m[i].m()
        m1 = line_m[i + 1].m()

        # Check if target_m is between m0 and m1
        if (m0 <= target_m <= m1) or (m1 <= target_m <= m0):
            # Interpolate
            if m0 == m1:
                # Degenerate case: use first point
                return QgsPointXY(line_m[i].x(), line_m[i].y())

            # Linear interpolation
            t = (target_m - m0) / (m1 - m0)
            x = line_m[i].x() + t * (line_m[i + 1].x() - line_m[i].x())
            y = line_m[i].y() + t * (line_m[i + 1].y() - line_m[i].y())
            return QgsPointXY(x, y)

    # target_m is out of range
    return None