from pathlib import Path
import sys

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessing,
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
from tree_qgis.RiverNetwork import RiverNetwork, PointsCollection, BrowsingStopper
from metatools.Solver1Dnormal import manning_solver, cs_solver


# =============================================================================
# Processing wrapper
# =============================================================================

class BedAssessment(QgsProcessingAlgorithm):

    ROUTES       = "ROUTES"
    RID_FIELD    = "RID_FIELD"
    ORDER_FIELD  = "ORDER_FIELD"
    LINKS        = "LINKS"
    POINTS       = "POINTS"
    ID_FIELD     = "ID_FIELD"
    RID_FIELD_PT = "RID_FIELD_PT"
    DIST_FIELD   = "DIST_FIELD"
    Q_FIELD      = "Q_FIELD"
    W_FIELD      = "W_FIELD"
    WS_FIELD     = "WS_FIELD"
    DEM_FIELD    = "DEM_FIELD"
    MANNING      = "MANNING"
    MIN_SLOPE    = "MIN_SLOPE"
    OUTPUT       = "OUTPUT"

    def name(self):
        return "bed_assessment"

    def displayName(self):
        return "Bed Assessment"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Metatools"

    def groupId(self):
        return "concordiariverlab_floodtools_metatools"

    def createInstance(self):
        return BedAssessment()

    def shortHelpString(self):
        return (
            "Bed Assessment\n\n"
            "Estimates bed elevation at each cross-section point using an inverse "
            "1D hydraulic approach (subcritical flow, direct solver). "
            "Requires channel width, LiDAR discharge, and smoothed water surface "
            "elevation at each point.\n\n"
            "Inputs:\n"
            "- Route feature class: oriented route network (e.g. routes_main)\n"
            "- RouteID field: RID\n"
            "- Order field: Qorder\n"
            "- Links table: DownID/UpID connectivity (e.g. routes_main_links)\n"
            "- Points: joined input points (e.g. bathy_input_pts)\n"
            "- ID field in points: id\n"
            "- RID field in points: RID\n"
            "- Distance field in points: MEAS\n"
            "- Discharge field: computedQLiDAR\n"
            "- Width field: Width\n"
            "- Water surface field: zws_smoothed\n"
            "- DEM ID field: ID_DEM\n"
            "- Manning's n coefficient (default 0.03)\n"
            "- Minimum energy slope in flat areas (default 0.00001)\n\n"
            "Output:\n"
            "- bathy_pts: input points with computed bed elevation (z) and "
            "hydraulic variables (y, R, v, h, s, Fr, solver)\n"
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessingParameterVectorLayer,
            QgsProcessingParameterField,
            QgsProcessingParameterNumber,
            QgsProcessingParameterFeatureSink,
        )

        self.addParameter(QgsProcessingParameterVectorLayer(
            self.ROUTES, "Route feature class (e.g. routes_main)",
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
            self.LINKS, "Links table (e.g. routes_main_links)",
            [QgsProcessing.TypeVector],
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.POINTS, "Points (e.g. bathy_input_pts)",
            [QgsProcessing.TypeVectorPoint, QgsProcessing.TypeVector],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.ID_FIELD, "ID field in points",
            parentLayerParameterName=self.POINTS,
            defaultValue="id",
        ))
        self.addParameter(QgsProcessingParameterField(
            self.RID_FIELD_PT, "RID field in points",
            parentLayerParameterName=self.POINTS,
            defaultValue="RID",
        ))
        self.addParameter(QgsProcessingParameterField(
            self.DIST_FIELD, "Distance field in points",
            parentLayerParameterName=self.POINTS,
            defaultValue="MEAS",
        ))
        self.addParameter(QgsProcessingParameterField(
            self.Q_FIELD, "Discharge field (computedQLiDAR)",
            parentLayerParameterName=self.POINTS,
            defaultValue="computedQLiDAR",
        ))
        self.addParameter(QgsProcessingParameterField(
            self.W_FIELD, "Width field",
            parentLayerParameterName=self.POINTS,
            defaultValue="Width",
        ))
        self.addParameter(QgsProcessingParameterField(
            self.WS_FIELD, "Water surface field (zws_smoothed)",
            parentLayerParameterName=self.POINTS,
            defaultValue="zws_smoothed",
        ))
        self.addParameter(QgsProcessingParameterField(
            self.DEM_FIELD, "DEM ID field",
            parentLayerParameterName=self.POINTS,
            defaultValue="ID_DEM",
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.MANNING, "Manning's n coefficient",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=0.03,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.MIN_SLOPE, "Minimum energy slope in flat areas",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=0.00001,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, "bathy_pts",
        ))

    def processAlgorithm(self, parameters, context, feedback):
        routes      = self.parameterAsVectorLayer(parameters, self.ROUTES, context)
        rid_field   = self.parameterAsString(parameters, self.RID_FIELD, context)
        order_field = self.parameterAsString(parameters, self.ORDER_FIELD, context)
        links       = self.parameterAsVectorLayer(parameters, self.LINKS, context)
        points      = self.parameterAsVectorLayer(parameters, self.POINTS, context)
        id_field    = self.parameterAsString(parameters, self.ID_FIELD, context)
        rid_pt      = self.parameterAsString(parameters, self.RID_FIELD_PT, context)
        dist_field  = self.parameterAsString(parameters, self.DIST_FIELD, context)
        q_field     = self.parameterAsString(parameters, self.Q_FIELD, context)
        w_field     = self.parameterAsString(parameters, self.W_FIELD, context)
        ws_field    = self.parameterAsString(parameters, self.WS_FIELD, context)
        dem_field   = self.parameterAsString(parameters, self.DEM_FIELD, context)
        manning     = self.parameterAsDouble(parameters, self.MANNING, context)
        min_slope   = self.parameterAsDouble(parameters, self.MIN_SLOPE, context)

        for lyr, name in [(routes, "Routes"), (links, "Links"), (points, "Points")]:
            if lyr is None:
                raise QgsProcessingException(f"{name} layer is invalid")

        results = execute_bed_assessment(
            routes=routes,
            rid_field=rid_field,
            order_field=order_field,
            links=links,
            points_layer=points,
            id_field=id_field,
            rid_field_pts=rid_pt,
            dist_field=dist_field,
            q_field=q_field,
            w_field=w_field,
            ws_field=ws_field,
            dem_field=dem_field,
            manning=manning,
            min_slope=min_slope,
            feedback=feedback,
        )

        out_fields = QgsFields()
        for f in points.fields():
            out_fields.append(f)
        for fname, ftype in [
            ("solver", QMetaType.QString),
            ("y",      QMetaType.Double),
            ("R",      QMetaType.Double),
            ("v",      QMetaType.Double),
            ("z",      QMetaType.Double),
            ("h",      QMetaType.Double),
            ("s",      QMetaType.Double),
            ("Fr",     QMetaType.Double),
        ]:
            if out_fields.indexFromName(fname) < 0:
                out_fields.append(QgsField(fname, ftype))

        (sink, sink_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context,
            out_fields,
            QgsWkbTypes.Point,
            points.sourceCrs(),
        )

        for row in results:
            if feedback.isCanceled():
                break
            f = QgsFeature(out_fields)
            x = row.get("X") or row.get("x")
            y_coord = row.get("Y") or row.get("y")
            if x is not None and y_coord is not None:
                try:
                    f.setGeometry(QgsGeometry.fromPointXY(
                        QgsPointXY(float(x), float(y_coord))
                    ))
                except (TypeError, ValueError):
                    pass
            f.setAttributes([row.get(field.name()) for field in out_fields])
            sink.addFeature(f, QgsFeatureSink.FastInsert)

        return {self.OUTPUT: sink_id}


# =============================================================================
# Core logic
# =============================================================================

g = 9.81


def execute_bed_assessment(
        routes,
        rid_field,
        order_field,
        links,
        points_layer,
        id_field,
        rid_field_pts,
        dist_field,
        q_field,
        w_field,
        ws_field,
        dem_field,
        manning,
        min_slope,
        feedback=None,
):
    network = RiverNetwork()
    network.load_data(routes, links, rid_field=rid_field)

    for reach in network._reaches.values():
        try:
            reach.order = int(getattr(reach, order_field, 0) or 0)
        except (TypeError, ValueError):
            reach.order = 0

    points_coll = PointsCollection(network, "data")
    points_coll.dict_attr_fields["id"]       = id_field
    points_coll.dict_attr_fields["reach_id"] = rid_field_pts
    points_coll.dict_attr_fields["dist"]     = dist_field
    points_coll.load_table(points_layer)

    pts_by_id = {int(feat[id_field]): feat for feat in points_layer.getFeatures()}

    for pt in points_coll._points.values():
        feat = pts_by_id.get(pt.id)
        if feat is None:
            continue
        for attr, field, default in [
            ("Q",       q_field,  0.0),
            ("width",   w_field,  1.0),
            ("wslidar", ws_field, 0.0),
        ]:
            try:
                setattr(pt, attr, float(feat[field]) if feat[field] is not None else default)
            except (TypeError, ValueError):
                setattr(pt, attr, default)
        pt.DEM = feat[dem_field]

        for f in points_layer.fields().names():
            if not hasattr(pt, f):
                val = feat[f]
                try:
                    setattr(pt, f, float(val) if val is not None else None)
                except (TypeError, ValueError):
                    setattr(pt, f, val)

        for attr in ("solver", "y", "R", "v", "z", "h", "s", "Fr"):
            setattr(pt, attr, None)

    # ── Step 1: compute slope (down to up) ────────────────────────────────────
    if feedback:
        feedback.pushInfo("Step 1/2: Computing slopes...")

    for reach in network.browse_reaches_down_to_up():
        if feedback and feedback.isCanceled():
            break
        prev_cs = None if reach.is_downstream_end() else getattr(
            reach.get_downstream_reach(), "last_point", None
        )
        cs = None
        for cs in reach.browse_points(points_coll):
            if prev_cs is not None:
                localdist = (
                    cs.dist - prev_cs.dist if cs.reach == prev_cs.reach
                    else prev_cs.reach.feature.geometry().length() - prev_cs.dist + cs.dist
                )
                cs.s = max(min_slope, (cs.wslidar - prev_cs.wslidar) / localdist) \
                    if localdist > 0 else min_slope
            else:
                cs.s = min_slope
            prev_cs = cs
        if cs is not None:
            reach.last_point = cs

    # ── Step 2: 1D hydraulic solver (up to down) ──────────────────────────────
    if feedback:
        feedback.pushInfo("Step 2/2: Running 1D hydraulic solver...")

    stopper      = BrowsingStopper()
    done_reaches = []

    for reach in network.browse_reaches_up_to_down(
        prioritize_reach_attribute="order",
        stopper=stopper,
    ):
        if feedback and feedback.isCanceled():
            break
        if reach.is_upstream_end():
            prev_cs = None
        if reach in done_reaches:
            stopper.break_generator = True
        else:
            for cs in reach.browse_points(points_coll, orientation="UP_TO_DOWN"):
                cs.n = manning
                if prev_cs is None:
                    manning_solver(cs)
                    cs.solver = "manning up"
                    cs.type   = 0
                elif prev_cs.DEM != cs.DEM:
                    cs.s      = prev_cs.s
                    manning_solver(cs)
                    cs.solver = "manning"
                    cs.type   = 0
                else:
                    cs.solver = "regular"
                    cs.type   = 1
                    _recursive_inverse_1d(cs, prev_cs, min_slope, points_coll)
                prev_cs = cs
            done_reaches.append(reach)

    output_fields = list(points_layer.fields().names()) + [
        "solver", "y", "R", "v", "z", "h", "s", "Fr"
    ]
    results = [{f: getattr(pt, f, None) for f in output_fields}
               for pt in points_coll._points.values()]

    if feedback:
        feedback.pushInfo(f"Done. Computed bed elevation for {len(results)} point(s).")

    return results


# =============================================================================
# Helpers
# =============================================================================

def _recursive_inverse_1d(cs, prev_cs, min_slope, points_coll):
    cs_solver(prev_cs, cs, min_slope)

    localdist = (
        prev_cs.dist - cs.dist if cs.reach == prev_cs.reach
        else cs.reach.feature.geometry().length() - cs.dist + prev_cs.dist
    )

    if (
        prev_cs.Fr is not None and prev_cs.Fr > 0
        and cs.Fr is not None
        and (cs.Fr - prev_cs.Fr) / prev_cs.Fr > 0.5
        and localdist > 0.1
    ):
        if cs.reach == prev_cs.reach:
            newcs = cs.reach.add_point((cs.dist + prev_cs.dist) / 2.0, points_coll)
        elif localdist / 2.0 < prev_cs.dist:
            newcs = prev_cs.reach.add_point(localdist / 2.0, points_coll)
        else:
            newcs = cs.reach.add_point(cs.dist + localdist / 2.0, points_coll)

        newlocaldist = localdist / 2.0
        for attr, cs_val, prev_val in [
            ("width",   cs.width,   prev_cs.width),
            ("Q",       cs.Q,       prev_cs.Q),
            ("wslidar", cs.wslidar, prev_cs.wslidar),
        ]:
            a = (cs_val - prev_val) / (0 - localdist)
            setattr(newcs, attr, a * newlocaldist + cs_val)

        newcs.n      = cs.n
        newcs.DEM    = prev_cs.DEM
        newcs.s      = cs.s
        newcs.solver = "regular"

        _recursive_inverse_1d(newcs, prev_cs, min_slope, points_coll)
        newcs.type = 3
        _recursive_inverse_1d(cs, newcs, min_slope, points_coll)