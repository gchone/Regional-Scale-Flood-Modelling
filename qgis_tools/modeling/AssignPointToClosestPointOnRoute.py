import numpy as np
from qgis.core import (
    QgsGeometry,
    QgsPointXY,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsFeatureSink,
    QgsFeature,
    QgsFields,
    QgsField,
    QgsWkbTypes,
    QgsProcessing,
)
from qgis.PyQt.QtCore import QMetaType


class AssignPointToClosestPointOnRoute(QgsProcessingAlgorithm):

    POINTS               = "POINTS"
    FIELDS_TO_KEEP       = "FIELDS_TO_KEEP"
    STAT                 = "STAT"
    ROUTES               = "ROUTES"
    ROUTES_ID_FIELD      = "ROUTES_ID_FIELD"
    POINTS_ON_ROUTE      = "POINTS_ON_ROUTE"
    POINTS_ON_ROUTE_RID  = "POINTS_ON_ROUTE_RID"
    POINTS_ON_ROUTE_DIST = "POINTS_ON_ROUTE_DIST"
    MATCHING_FIELDS_PTS  = "MATCHING_FIELDS_PTS"
    MATCHING_FIELDS_TGT  = "MATCHING_FIELDS_TGT"
    OUTPUT               = "OUTPUT"

    STAT_OPTIONS = ["MEAN", "CLOSEST", "MAX", "2-WAY CLOSEST"]

    def name(self):
        return "assignpointtoclosestpointonroute"

    def displayName(self):
        return "Assign point to closest point on route"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Modeling"

    def groupId(self):
        return "concordiariverlab_floodtools_modeling"

    def createInstance(self):
        return AssignPointToClosestPointOnRoute()

    def shortHelpString(self):
        return (
            "Assign point to closest point on route\n\n"
            "Projects a point layer to the closest point on a network. "
            "Both input layers (points and points on network) must have a RouteID field.\n\n"
            "Inputs:\n"
            "- Points feature class: data points to project (ws_pathpointsD8)\n"
            "- Fields to keep: fields from data points to transfer to output\n"
            "- Aggregation method: how to aggregate when multiple data points match a target point\n"
            "- Route feature class: oriented route network\n"
            "- RouteID field: RID\n"
            "- Points on route: target points on network (target_pts)\n"
            "- RouteID field in target points: RID\n"
            "- Distance field in target points: MEAS\n"
            "- Fields to match in data points: fields used to group matches (e.g. RID)\n"
            "- Fields to match in target points: corresponding fields in target points\n\n"
            "Output:\n"
            "- Target points with data fields assigned\n"
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessingParameterVectorLayer,
            QgsProcessingParameterField,
            QgsProcessingParameterEnum,
            QgsProcessingParameterFeatureSink,
        )

        self.addParameter(QgsProcessingParameterVectorLayer(
            self.POINTS, "Points feature class (ws_pathpointsD8)",
            [QgsProcessing.TypeVectorPoint],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.FIELDS_TO_KEEP, "Fields to keep in output (lidar3m_forws)",
            parentLayerParameterName=self.POINTS,
            allowMultiple=True,
        ))
        self.addParameter(QgsProcessingParameterEnum(
            self.STAT, "Aggregation method",
            options=self.STAT_OPTIONS,
            defaultValue=3,  # 2-WAY CLOSEST
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.ROUTES, "Route feature class",
            [QgsProcessing.TypeVectorLine],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.ROUTES_ID_FIELD, "RouteID field in route feature class",
            parentLayerParameterName=self.ROUTES,
            defaultValue="RID",
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.POINTS_ON_ROUTE, "Points on route (target_pts)",
            [QgsProcessing.TypeVectorPoint],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.POINTS_ON_ROUTE_RID, "RouteID field in target points",
            parentLayerParameterName=self.POINTS_ON_ROUTE,
            defaultValue="RID",
        ))
        self.addParameter(QgsProcessingParameterField(
            self.POINTS_ON_ROUTE_DIST, "Distance field in target points",
            parentLayerParameterName=self.POINTS_ON_ROUTE,
            defaultValue="MEAS",
        ))
        self.addParameter(QgsProcessingParameterField(
            self.MATCHING_FIELDS_PTS, "Fields to match in data points (RID)",
            parentLayerParameterName=self.POINTS,
            allowMultiple=True,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.MATCHING_FIELDS_TGT, "Fields to match in target points (RID)",
            parentLayerParameterName=self.POINTS_ON_ROUTE,
            allowMultiple=True,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, "Output point layer",
        ))

    def processAlgorithm(self, parameters, context, feedback):
        data_layer    = self.parameterAsVectorLayer(parameters, self.POINTS, context)
        fields_to_keep = self.parameterAsFields(parameters, self.FIELDS_TO_KEEP, context)
        stat_idx      = self.parameterAsEnum(parameters, self.STAT, context)
        stat          = self.STAT_OPTIONS[stat_idx]
        routes        = self.parameterAsVectorLayer(parameters, self.ROUTES, context)
        rid_field     = self.parameterAsString(parameters, self.ROUTES_ID_FIELD, context)
        target_layer  = self.parameterAsVectorLayer(parameters, self.POINTS_ON_ROUTE, context)
        target_rid    = self.parameterAsString(parameters, self.POINTS_ON_ROUTE_RID, context)
        target_dist   = self.parameterAsString(parameters, self.POINTS_ON_ROUTE_DIST, context)
        match_pts     = self.parameterAsFields(parameters, self.MATCHING_FIELDS_PTS, context)
        match_tgt     = self.parameterAsFields(parameters, self.MATCHING_FIELDS_TGT, context)

        if data_layer is None:
            raise QgsProcessingException("Data points layer is invalid")
        if target_layer is None:
            raise QgsProcessingException("Target points layer is invalid")
        if routes is None:
            raise QgsProcessingException("Routes layer is invalid")

        # Load data points as list of dicts
        data_points = []
        for feat in data_layer.getFeatures():
            pt = feat.geometry().asPoint()
            d = {"X": pt.x(), "Y": pt.y()}
            for f in data_layer.fields().names():
                d[f] = feat[f]
            data_points.append(d)

        # Load target points as list of dicts
        target_points = []
        for feat in target_layer.getFeatures():
            pt = feat.geometry().asPoint()
            d = {"X": pt.x(), "Y": pt.y()}
            for f in target_layer.fields().names():
                d[f] = feat[f]
            target_points.append(d)

        # Load routes as dict of rid -> geometry
        routes_geoms = {}
        for feat in routes.getFeatures():
            routes_geoms[int(feat[rid_field])] = feat.geometry()

        results = assign_point_to_closest_point_on_route(
            data_points=data_points,
            data_fields=fields_to_keep,
            data_matching_fields=match_pts,
            target_points=target_points,
            target_rid_field=target_rid,
            target_dist_field=target_dist,
            target_matching_fields=match_tgt,
            routes=routes_geoms,
            rid_field=rid_field,
            stat=stat,
            feedback=feedback,
        )

        # Build output fields from target layer + kept data fields + NEAR_DIST
        out_fields = QgsFields()
        for f in target_layer.fields():
            out_fields.append(f)
        for f in fields_to_keep:
            if out_fields.indexFromName(f) < 0:
                out_fields.append(QgsField(f, QMetaType.Double))
        out_fields.append(QgsField("NEAR_DIST", QMetaType.Double))

        (sink, sink_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context,
            out_fields,
            QgsWkbTypes.Point,
            target_layer.sourceCrs(),
        )

        for res in results:
            if feedback.isCanceled():
                break
            f = QgsFeature(out_fields)
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(res["X"], res["Y"])))
            attrs = []
            for field in out_fields:
                attrs.append(res.get(field.name()))
            f.setAttributes(attrs)
            sink.addFeature(f, QgsFeatureSink.FastInsert)

        return {self.OUTPUT: sink_id}


# =============================================================================
# Core logic
# =============================================================================

def assign_point_to_closest_point_on_route(
    data_points, data_fields, data_matching_fields,
    target_points, target_rid_field, target_dist_field, target_matching_fields,
    routes, rid_field,
    stat="2-WAY CLOSEST",
    feedback=None
):
    """
    For each target point (on route), finds the closest data point on the same reach
    and assigns its field values. Mirrors ArcGIS execute_AssignPointToClosestPointOnRoute.

    Parameters
    ----------
    data_points          : list of dicts — data points with X, Y, and field values
    data_fields          : list of str — field names to transfer from data points to target points
    data_matching_fields : list of str — fields used to match data points to target points
    target_points        : list of dicts — target points with rid, dist, and matching fields
    target_rid_field     : str — RID field name in target points
    target_dist_field    : str — distance field name in target points
    target_matching_fields : list of str — fields used to match target points to data points
    routes               : dict of rid -> QgsGeometry
    rid_field            : str — RID field name in routes
    stat                 : str — '2-WAY CLOSEST', 'MEAN', 'MAX', 'CLOSEST'
    feedback             : QgsProcessingFeedback or None

    Returns
    -------
    list of dicts — target points with data fields assigned
    """
    data_match_set = set(
        tuple(pt[f] for f in data_matching_fields)
        for pt in data_points
    )
    target_match_set = set(
        tuple(pt[f] for f in target_matching_fields)
        for pt in target_points
    )
    common_matches = data_match_set & target_match_set

    if feedback:
        feedback.pushInfo(f"Found {len(common_matches)} matching group(s)")

    data_by_match = {}
    for pt in data_points:
        key = tuple(pt[f] for f in data_matching_fields)
        data_by_match.setdefault(key, []).append(pt)

    target_by_match = {}
    for pt in target_points:
        key = tuple(pt[f] for f in target_matching_fields)
        target_by_match.setdefault(key, []).append(pt)

    results = []

    for match_key in common_matches:
        d_pts = data_by_match.get(match_key, [])
        t_pts = target_by_match.get(match_key, [])

        if not d_pts or not t_pts:
            continue

        if stat == "2-WAY CLOSEST":
            # Project each data point onto the route geometry and get its linear position
            # Then for each target point, find the data point with closest linear position

            # Build linear positions for data points on their route
            data_linear = []
            for d_pt in d_pts:
                d_geom = QgsGeometry.fromPointXY(QgsPointXY(d_pt["X"], d_pt["Y"]))
                # Get the RID for this data point from matching fields
                rid = match_key[0] if len(match_key) == 1 else None
                route_geom = routes.get(int(rid)) if rid is not None else None
                if route_geom:
                    # Project point onto route and get linear distance along route
                    linear_pos = route_geom.lineLocatePoint(d_geom)
                else:
                    # Fall back to using dist field if available
                    linear_pos = float(d_pt.get("dist", 0) or 0)
                data_linear.append((linear_pos, d_pt))

            for t_pt in t_pts:
                t_linear = float(t_pt.get(target_dist_field, 0) or 0)
                min_dist = float('inf')
                closest_d = None
                for linear_pos, d_pt in data_linear:
                    dist = abs(linear_pos - t_linear)
                    if dist < min_dist:
                        min_dist = dist
                        closest_d = d_pt
                result = {k: v for k, v in t_pt.items() if not k.startswith("_")}
                if closest_d is not None:
                    for f in data_fields:
                        result[f] = closest_d[f]
                    result["NEAR_DIST"] = min_dist
                else:
                    for f in data_fields:
                        result[f] = None
                    result["NEAR_DIST"] = None
                results.append(result)

        else:
            for t_pt in t_pts:
                t_geom = QgsGeometry.fromPointXY(QgsPointXY(t_pt["X"], t_pt["Y"]))
                min_dist = float('inf')
                closest_d = None
                for d_pt in d_pts:
                    d_geom = QgsGeometry.fromPointXY(QgsPointXY(d_pt["X"], d_pt["Y"]))
                    dist = t_geom.distance(d_geom)
                    if dist < min_dist:
                        min_dist = dist
                        closest_d = d_pt

                result = {k: v for k, v in t_pt.items()}
                if closest_d is not None:
                    for f in data_fields:
                        result[f] = closest_d[f]
                else:
                    for f in data_fields:
                        result[f] = None
                results.append(result)

    if feedback:
        feedback.pushInfo(f"Assigned values to {len(results)} target point(s)")

    return results