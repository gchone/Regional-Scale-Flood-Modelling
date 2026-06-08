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
            "Both input layers (points and points on network) must have a RouteID field.\n"
            "This tool is used at multiple steps in the workflow.\n\n"
            "Inputs:\n"
            "- Points feature class: data points to project (e.g. ws_pathpointsD8, Qpts_spatialized_D8, bathy_on_mainroute)\n"
            "- Fields to keep: fields from data points to transfer to output (e.g. lidar3m_forws, computedQLiDAR, z)\n"
            "- Aggregation method: how to aggregate when multiple data points match a target point (e.g. 2-WAY CLOSEST, CLOSEST, MAX)\n"
            "- Route feature class: oriented route network (e.g. routes_main, routesD4)\n"
            "- RouteID field: RID\n"
            "- Points on route: target points on network (e.g. target_pts, smoothed_pts, pathpointsD4_geom)\n"
            "- RouteID field in target points: RID\n"
            "- Distance field in target points: MEAS or dist\n"
            "- Fields to match in data points: fields used to group matches (e.g. RID, ID_DEM or RID_routesmain, ID_DEM or RID_1)\n"
            "- Fields to match in target points: corresponding fields in target points (e.g. RID, ID_DEM)\n\n"
            "IMPORTANT: The fields to match must be listed in the same order in both layers.\n\n"
            "Output:\n"
            "- Target points with data fields assigned (e.g. Qpts_spatialized, bathy_on_D4)\n"
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessingParameterVectorLayer,
            QgsProcessingParameterField,
            QgsProcessingParameterEnum,
            QgsProcessingParameterFeatureSink,
        )

        self.addParameter(QgsProcessingParameterVectorLayer(
            self.POINTS, "Points feature class (e.g. ws_pathpointsD8, Qpts_spatialized_D8, bathy_on_mainroute)",
            [QgsProcessing.TypeVectorPoint],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.FIELDS_TO_KEEP, "Fields to keep in output (e.g. lidar3m_forws, computedQLiDAR, z)",
            parentLayerParameterName=self.POINTS,
            allowMultiple=True,
        ))
        self.addParameter(QgsProcessingParameterEnum(
            self.STAT, "Aggregation method",
            options=self.STAT_OPTIONS,
            defaultValue=1,  # CLOSEST
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.ROUTES, "Route feature class (e.g. routes_main, routesD4)",
            [QgsProcessing.TypeVectorLine],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.ROUTES_ID_FIELD, "RouteID field in route feature class",
            parentLayerParameterName=self.ROUTES,
            defaultValue="RID",
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.POINTS_ON_ROUTE, "Points on route (e.g. target_pts, smoothed_pts, pathpointsD4_geom)",
            [QgsProcessing.TypeVectorPoint],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.POINTS_ON_ROUTE_RID, "RouteID field in target points",
            parentLayerParameterName=self.POINTS_ON_ROUTE,
            defaultValue="RID",
        ))
        self.addParameter(QgsProcessingParameterField(
            self.POINTS_ON_ROUTE_DIST, "Distance field in target points (e.g. MEAS, dist)",
            parentLayerParameterName=self.POINTS_ON_ROUTE,
            defaultValue="MEAS",
        ))
        self.addParameter(QgsProcessingParameterField(
            self.MATCHING_FIELDS_PTS,
            "Fields to match in data points (e.g. RID_routesmain, ID_DEM, RID_1 — order matters)",
            parentLayerParameterName=self.POINTS,
            allowMultiple=True,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.MATCHING_FIELDS_TGT, "Fields to match in target points (e.g. RID, ID_DEM — must match order above)",
            parentLayerParameterName=self.POINTS_ON_ROUTE,
            allowMultiple=True,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, "Output points (e.g. Qpts_spatialized, bathy_on_D4)",
        ))

    def processAlgorithm(self, parameters, context, feedback):
        data_layer     = self.parameterAsVectorLayer(parameters, self.POINTS, context)
        fields_to_keep = self.parameterAsFields(parameters, self.FIELDS_TO_KEEP, context)
        stat_idx       = self.parameterAsEnum(parameters, self.STAT, context)
        stat           = self.STAT_OPTIONS[stat_idx]
        routes         = self.parameterAsVectorLayer(parameters, self.ROUTES, context)
        rid_field      = self.parameterAsString(parameters, self.ROUTES_ID_FIELD, context)
        target_layer   = self.parameterAsVectorLayer(parameters, self.POINTS_ON_ROUTE, context)
        target_rid     = self.parameterAsString(parameters, self.POINTS_ON_ROUTE_RID, context)
        target_dist    = self.parameterAsString(parameters, self.POINTS_ON_ROUTE_DIST, context)
        match_pts      = self.parameterAsFields(parameters, self.MATCHING_FIELDS_PTS, context)
        match_tgt      = self.parameterAsFields(parameters, self.MATCHING_FIELDS_TGT, context)

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
        if stat != "CLOSEST":
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
    data_points            : list of dicts — data points with X, Y, and field values
    data_fields            : list of str — field names to transfer from data points to target points
    data_matching_fields   : list of str — fields used to match data points to target points
    target_points          : list of dicts — target points with rid, dist, and matching fields
    target_rid_field       : str — RID field name in target points
    target_dist_field      : str — distance field name in target points
    target_matching_fields : list of str — fields used to match target points to data points
    routes                 : dict of rid -> QgsGeometry
    rid_field              : str — RID field name in routes
    stat                   : str — '2-WAY CLOSEST', 'MEAN', 'MAX', 'CLOSEST'
    feedback               : QgsProcessingFeedback or None

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
            # Build linear positions for data points on their route
            data_linear = []
            for d_pt in d_pts:
                d_geom = QgsGeometry.fromPointXY(QgsPointXY(d_pt["X"], d_pt["Y"]))
                rid = match_key[0] if len(match_key) == 1 else None
                route_geom = routes.get(int(rid)) if rid is not None else None
                if route_geom:
                    linear_pos = route_geom.lineLocatePoint(d_geom)
                else:
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

        elif stat == "MEAN" or stat == "MAX":
            # For each data point, find its closest target point.
            # Then group data points by the target point they mapped to,
            # and aggregate field values (mean or max) for each target point.
            # Mirrors ArcGIS: GenerateNearTable from points_lyr to onroute_lyr,
            # then group by target OID and aggregate.
            t_geoms = [QgsGeometry.fromPointXY(QgsPointXY(t["X"], t["Y"])) for t in t_pts]

            # For each data point, find closest target point
            target_to_data = {}  # target index -> list of data points
            near_dists = {}      # target index -> list of near distances
            for d_pt in d_pts:
                d_geom = QgsGeometry.fromPointXY(QgsPointXY(d_pt["X"], d_pt["Y"]))
                min_dist = float('inf')
                closest_t_idx = None
                for t_idx, t_geom in enumerate(t_geoms):
                    dist = d_geom.distance(t_geom)
                    if dist < min_dist:
                        min_dist = dist
                        closest_t_idx = t_idx
                if closest_t_idx is not None:
                    target_to_data.setdefault(closest_t_idx, []).append(d_pt)
                    near_dists.setdefault(closest_t_idx, []).append(min_dist)

            for t_idx, t_pt in enumerate(t_pts):
                result = {k: v for k, v in t_pt.items()}
                mapped_d_pts = target_to_data.get(t_idx, [])

                # Fallback: if no data point mapped to this target, find closest data point directly
                if not mapped_d_pts:
                    t_geom = t_geoms[t_idx]
                    min_dist = float('inf')
                    closest_d = None
                    for d_pt in d_pts:
                        d_geom = QgsGeometry.fromPointXY(QgsPointXY(d_pt["X"], d_pt["Y"]))
                        dist = t_geom.distance(d_geom)
                        if dist < min_dist:
                            min_dist = dist
                            closest_d = d_pt
                    if closest_d is not None:
                        mapped_d_pts = [closest_d]
                        near_dists[t_idx] = [min_dist]

                if mapped_d_pts:
                    for f in data_fields:
                        vals = []
                        for d_pt in mapped_d_pts:
                            v = d_pt.get(f)
                            if v is not None:
                                try:
                                    vals.append(float(v))
                                except (TypeError, ValueError):
                                    pass
                        if vals:
                            result[f] = float(np.mean(vals)) if stat == "MEAN" else float(np.max(vals))
                        else:
                            result[f] = None
                    result["NEAR_DIST"] = float(np.mean(near_dists[t_idx]))
                else:
                    for f in data_fields:
                        result[f] = None
                    result["NEAR_DIST"] = None
                results.append(result)

        else:
            # CLOSEST: for each target point find the single closest data point
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