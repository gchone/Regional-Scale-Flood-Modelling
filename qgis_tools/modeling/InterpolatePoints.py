import numpy as np
from pathlib import Path
import sys
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
from qgis.PyQt.QtCore import QMetaType, QVariant


class InterpolatePoints(QgsProcessingAlgorithm):

    POINTS_TABLE       = "POINTS_TABLE"
    PTS_ID_FIELD       = "PTS_ID_FIELD"
    PTS_RID_FIELD      = "PTS_RID_FIELD"
    PTS_DIST_FIELD     = "PTS_DIST_FIELD"
    DATA_FIELDS        = "DATA_FIELDS"
    TARGETS            = "TARGETS"
    TARGETS_ID_FIELD   = "TARGETS_ID_FIELD"
    TARGETS_RID_FIELD  = "TARGETS_RID_FIELD"
    TARGETS_DIST_FIELD = "TARGETS_DIST_FIELD"
    ROUTES             = "ROUTES"
    RID_FIELD          = "RID_FIELD"
    ORDER_FIELD        = "ORDER_FIELD"
    LINKS              = "LINKS"
    OUTPUT             = "OUTPUT"

    def name(self):
        return "interpolatepoints"

    def displayName(self):
        return "Interpolate points"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Modeling"

    def groupId(self):
        return "concordiariverlab_floodtools_modeling"

    def createInstance(self):
        return InterpolatePoints()

    def shortHelpString(self):
        return (
            "Interpolate points\n\n"
            "Interpolates values from data points onto target points along the river network. "
            "Interpolation is done reach by reach, crossing reach boundaries when needed "
            "by looking upstream and downstream for the nearest data points.\n\n"
            "Used in both the width workflow (width_pts → width_postpro) and the "
            "water surface workflow.\n\n"
            "Inputs:\n"
            "- Data points table: points with values to interpolate (e.g. width_pts, bathy_on_D4)\n"
            "- ID field in data points: unique identifier (e.g. id, ObjectID_1)\n"
            "- RID field in data points: RouteID (e.g. RID)\n"
            "- Distance field in data points: MEAS\n"
            "- Fields to interpolate: fields with values to interpolate (e.g. Width, z)\n"
            "- Target points: points to interpolate onto (e.g. smoothed_pts, pathpointsD4)\n"
            "- ID field in target points: unique identifier (e.g. id, ObjectID_1)\n"
            "- RID field in target points: RouteID (e.g. RID)\n"
            "- Distance field in target points: MEAS\n"
            "- Route feature class: oriented route network (e.g. routes_main, routesD4)\n"
            "- RouteID field: RID\n"
            "- Order field: Qorder\n"
            "- Links table: DownID/UpID connectivity (e.g. routes_main_links, linksD4)\n\n"
            "Output:\n"
            "- Target points with interpolated values (e.g. width_postpro, bathy_final)\n"
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessingParameterVectorLayer,
            QgsProcessingParameterField,
            QgsProcessingParameterFeatureSink,
        )

        self.addParameter(QgsProcessingParameterVectorLayer(
            self.POINTS_TABLE, "Data points table (e.g. width_pts, bathy_on_D4)",
            [QgsProcessing.TypeVectorPoint, QgsProcessing.TypeVector],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.PTS_ID_FIELD, "ID field in data points (e.g. id, ObjectID_1)",
            parentLayerParameterName=self.POINTS_TABLE,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.PTS_RID_FIELD, "RID field in data points",
            parentLayerParameterName=self.POINTS_TABLE,
            defaultValue="RID",
        ))
        self.addParameter(QgsProcessingParameterField(
            self.PTS_DIST_FIELD, "Distance field in data points",
            parentLayerParameterName=self.POINTS_TABLE,
            defaultValue="MEAS",
        ))
        self.addParameter(QgsProcessingParameterField(
            self.DATA_FIELDS, "Fields to interpolate (e.g. Width, z)",
            parentLayerParameterName=self.POINTS_TABLE,
            allowMultiple=True,
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.TARGETS, "Target points (e.g. smoothed_pts, pathpointsD4)",
            [QgsProcessing.TypeVectorPoint, QgsProcessing.TypeVector],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.TARGETS_ID_FIELD, "ID field in target points (e.g. id, ObjectID_1)",
            parentLayerParameterName=self.TARGETS,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.TARGETS_RID_FIELD, "RID field in target points",
            parentLayerParameterName=self.TARGETS,
            defaultValue="RID",
        ))
        self.addParameter(QgsProcessingParameterField(
            self.TARGETS_DIST_FIELD, "Distance field in target points",
            parentLayerParameterName=self.TARGETS,
            defaultValue="MEAS",
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.ROUTES, "Route feature class (e.g. routes_main, routesD4)",
            [QgsProcessing.TypeVectorLine],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.RID_FIELD, "RouteID field",
            parentLayerParameterName=self.ROUTES,
            defaultValue="RID",
        ))
        self.addParameter(QgsProcessingParameterField(
            self.ORDER_FIELD, "Order field",
            parentLayerParameterName=self.ROUTES,
            defaultValue="Qorder",
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.LINKS, "Links table (e.g. routes_main_links, linksD4)",
            [QgsProcessing.TypeVector],
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, "Output interpolated points (e.g. width_postpro, bathy_final)",
        ))

    def processAlgorithm(self, parameters, context, feedback):
        pts_layer      = self.parameterAsVectorLayer(parameters, self.POINTS_TABLE, context)
        pts_id         = self.parameterAsString(parameters, self.PTS_ID_FIELD, context)
        pts_rid        = self.parameterAsString(parameters, self.PTS_RID_FIELD, context)
        pts_dist       = self.parameterAsString(parameters, self.PTS_DIST_FIELD, context)
        data_fields    = self.parameterAsFields(parameters, self.DATA_FIELDS, context)
        targets_layer  = self.parameterAsVectorLayer(parameters, self.TARGETS, context)
        tgt_id         = self.parameterAsString(parameters, self.TARGETS_ID_FIELD, context)
        tgt_rid        = self.parameterAsString(parameters, self.TARGETS_RID_FIELD, context)
        tgt_dist       = self.parameterAsString(parameters, self.TARGETS_DIST_FIELD, context)
        routes         = self.parameterAsVectorLayer(parameters, self.ROUTES, context)
        rid_field      = self.parameterAsString(parameters, self.RID_FIELD, context)
        order_field    = self.parameterAsString(parameters, self.ORDER_FIELD, context)
        links          = self.parameterAsVectorLayer(parameters, self.LINKS, context)

        if pts_layer is None:
            raise QgsProcessingException("Data points layer is invalid")
        if targets_layer is None:
            raise QgsProcessingException("Target points layer is invalid")
        if routes is None:
            raise QgsProcessingException("Routes layer is invalid")
        if links is None:
            raise QgsProcessingException("Links layer is invalid")

        # Load data points
        data_points = []
        for feat in pts_layer.getFeatures():
            d = {}
            for f in pts_layer.fields().names():
                val = feat[f]
                d[f] = None if isinstance(val, QVariant) or (hasattr(val, 'isNull') and val.isNull()) else val
            data_points.append(d)

        # Load target points
        target_points = []
        for feat in targets_layer.getFeatures():
            d = {}
            for f in targets_layer.fields().names():
                val = feat[f]
                d[f] = None if isinstance(val, QVariant) or (hasattr(val, 'isNull') and val.isNull()) else val
            if feat.geometry() and not feat.geometry().isEmpty():
                pt = feat.geometry().asPoint()
                d["X"] = pt.x()
                d["Y"] = pt.y()
            target_points.append(d)

        # Load reaches
        reaches = {}
        for feat in routes.getFeatures():
            rid = int(feat[rid_field])
            reaches[rid] = {
                "length": feat.geometry().length(),
                "order":  int(feat[order_field]) if feat[order_field] is not None else 0,
            }

        # Load links
        downstream = {}  # rid -> down_rid
        upstream = {}    # rid -> [up_rids]
        for feat in links.getFeatures():
            down_id = int(feat["DownID"])
            up_id   = int(feat["UpID"])
            downstream[up_id] = down_id
            upstream.setdefault(down_id, []).append(up_id)

        result_rows = interpolate_points(
            data_points=data_points,
            pts_id=pts_id,
            pts_rid=pts_rid,
            pts_dist=pts_dist,
            data_fields=data_fields,
            target_points=target_points,
            tgt_id=tgt_id,
            tgt_rid=tgt_rid,
            tgt_dist=tgt_dist,
            reaches=reaches,
            downstream=downstream,
            upstream=upstream,
            feedback=feedback,
        )

        # Build output fields
        out_fields = QgsFields()
        for f in targets_layer.fields():
            out_fields.append(f)
        for f in data_fields:
            if out_fields.indexFromName(f) < 0:
                out_fields.append(QgsField(f, QMetaType.Double))

        (sink, sink_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context,
            out_fields,
            QgsWkbTypes.Point,
            targets_layer.sourceCrs(),
        )

        for row in result_rows:
            if feedback.isCanceled():
                break
            f = QgsFeature(out_fields)
            if "X" in row and "Y" in row:
                f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(row["X"], row["Y"])))
            attrs = [row.get(field.name()) for field in out_fields]
            f.setAttributes(attrs)
            sink.addFeature(f, QgsFeatureSink.FastInsert)

        return {self.OUTPUT: sink_id}


def interpolate_points(
    data_points, pts_id, pts_rid, pts_dist, data_fields,
    target_points, tgt_id, tgt_rid, tgt_dist,
    reaches, downstream, upstream,
    extrapolation_value=None,
    feedback=None
):
    """
    Interpolates values from data points onto target points along the river network.
    Mirrors ArcGIS InterpolatePoints_with_objects.

    Parameters
    ----------
    data_points       : list of dicts — points with values to interpolate
    pts_id            : str — ID field name in data points
    pts_rid           : str — RID field name in data points
    pts_dist          : str — distance field name in data points
    data_fields       : list of str — fields to interpolate
    target_points     : list of dicts — points to interpolate onto
    tgt_id            : str — ID field name in target points
    tgt_rid           : str — RID field name in target points
    tgt_dist          : str — distance field name in target points
    reaches           : dict of rid -> {'length': float, 'order': int}
    downstream        : dict of rid -> down_rid
    upstream          : dict of rid -> [up_rids]
    extrapolation_value : None or float or 'CONFLUENCE'
    feedback          : QgsProcessingFeedback or None

    Returns
    -------
    list of dicts — target points with interpolated fields added
    """
    all_rids = set(reaches.keys())
    downstream_ends = all_rids - set(downstream.keys())

    def browse_down_to_up(rid):
        yield rid
        for up_rid in sorted(upstream.get(rid, []),
                             key=lambda r: reaches[r]["order"]):
            yield from browse_down_to_up(up_rid)

    # Index data points by rid
    data_by_rid = {}
    for pt in data_points:
        rid = int(pt[pts_rid])
        data_by_rid.setdefault(rid, []).append(pt)

    # Index target points by rid
    target_by_rid = {}
    for pt in target_points:
        rid = int(pt[tgt_rid])
        target_by_rid.setdefault(rid, []).append(pt)

    results = []

    for end_rid in downstream_ends:
        for rid in browse_down_to_up(end_rid):
            reach = reaches.get(rid)
            if reach is None:
                continue

            # Get target points for this reach sorted by distance
            t_pts = sorted(
                target_by_rid.get(rid, []),
                key=lambda p: float(p[tgt_dist])
            )
            if not t_pts:
                continue

            # Get data points for this reach sorted by distance
            d_pts = sorted(
                data_by_rid.get(rid, []),
                key=lambda p: float(p[pts_dist])
            )

            # Look downstream for boundary point
            down_pts = list(d_pts)
            down_reach_rid = downstream.get(rid)
            same_order = reach["order"]
            downend = down_reach_rid is None

            while not downend and len(down_pts) == 0:
                down_reach = reaches.get(down_reach_rid)
                if down_reach is None:
                    break
                same_order -= 1
                if extrapolation_value != "CONFLUENCE" or down_reach["order"] == same_order:
                    down_d_pts = sorted(
                        data_by_rid.get(down_reach_rid, []),
                        key=lambda p: float(p[pts_dist])
                    )
                    if down_d_pts:
                        # Take last (most upstream) point in downstream reach
                        # and adjust its distance
                        boundary_pt = dict(down_d_pts[-1])
                        boundary_pt[pts_dist] = float(boundary_pt[pts_dist]) - down_reach["length"]
                        down_pts = [boundary_pt] + down_pts
                    downend = down_reach_rid not in downstream
                    down_reach_rid = downstream.get(down_reach_rid)
                else:
                    downend = True

            # Look upstream for boundary point
            up_pts = list(d_pts)
            up_rid = rid
            upend = up_rid not in upstream

            while not upend and len(up_pts) == 0:
                up_candidates = upstream.get(up_rid, [])
                if not up_candidates:
                    break
                # Follow the upstream reach with smallest order
                up_rid = min(up_candidates, key=lambda r: reaches.get(r, {}).get("order", 999))
                up_d_pts = sorted(
                    data_by_rid.get(up_rid, []),
                    key=lambda p: float(p[pts_dist])
                )
                if up_d_pts:
                    boundary_pt = dict(up_d_pts[0])
                    boundary_pt[pts_dist] = float(boundary_pt[pts_dist]) + reach["length"]
                    up_pts = up_pts + [boundary_pt]
                upend = up_rid not in upstream

            sorted_data = sorted(down_pts + up_pts,
                                 key=lambda p: float(p[pts_dist]))

            # Interpolate each field for each target point
            if extrapolation_value is None or extrapolation_value == "CONFLUENCE":
                left_right = None
            else:
                left_right = float(extrapolation_value)

            for t_pt in t_pts:
                result = dict(t_pt)
                if len(sorted_data) > 0:
                    x_t = float(t_pt[tgt_dist])
                    for field in data_fields:
                        valid_data = [p for p in sorted_data if p.get(field) is not None]
                        if valid_data:
                            x_data = np.array([float(p[pts_dist]) for p in valid_data])
                            y_data = np.array([float(p[field]) for p in valid_data])
                            val = float(np.interp(x_t, x_data, y_data,
                                                  left=left_right, right=left_right))
                        else:
                            val = float(extrapolation_value) if extrapolation_value is not None else None
                        result[field] = val
                else:
                    for field in data_fields:
                        result[field] = float(extrapolation_value) if extrapolation_value is not None else None
                results.append(result)

    if feedback:
        feedback.pushInfo(f"Interpolated values for {len(results)} target point(s)")

    return results