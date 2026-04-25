from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from osgeo import gdal
import numpy as np

from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsFields,
    QgsField,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QMetaType

from tree_qgis.TreeTools import create_from_points_and_splits, tree_from_flowdir
from modeling.RelateNetworks import relate_networks
from modeling.LocateMostDownstreamPoints import locate_most_downstream_points
from modeling.LocatePointsAlongRoutes import locate_points_along_routes
from tree_qgis.RiverNetwork import RiverNetwork, PointsCollection, DataPoint

# =============================================================================
# Meta functions
# =============================================================================

def flow_direction_network(routes, links, rid_field, r_flow_dir, feedback=None):
    """
    Orchestrates the full Flow Direction Network workflow.

    Steps:
        1. create_from_points_and_splits() — classify headwater and split-point
           seeds from the oriented route network
        2. tree_from_flowdir()             — trace D8 flow paths from seeds,
           building D8-snapped routes, links, and path points
        3. relate_networks()               — relate original routes to D8 routes
           by intersection point count

    Args:
        routes     : QgsVectorLayer (lines) — oriented route network
        links      : QgsFeatureSource — DownID/UpID link table
        rid_field  : str — RouteID field name (shared by routes and D8 output)
        r_flow_dir : QgsRasterLayer — D8 flow direction raster
        feedback   : QgsProcessingFeedback or None

    Returns:
        routed8_features : list of QgsFeature (lines)
        linksd8_rows     : list of (downRID, upRID)
        ptsond8_rows     : list of (id, RID, dist, offset, X, Y, row, col)
        relate_rows      : list of (rid_a, rid_b, part_count)
    """

    if feedback:
        feedback.pushInfo("Step 1/3: Building from-points and split-points…")

    fp_features, split_features = create_from_points_and_splits(
        routes=routes,
        links=links,
        rid_field=rid_field,
        feedback=feedback,
    )

    if feedback:
        feedback.pushInfo("Step 2/3: Tracing D8 flow paths…")

    routed8_features, linksd8_rows, ptsond8_rows = tree_from_flowdir(
        r_flow_dir=r_flow_dir,
        fp_features=fp_features,
        split_features=split_features,
        rid_field=rid_field,
        crs=routes.sourceCrs(),
        tolerance=10000,
        feedback=feedback,
    )

    if feedback:
        feedback.pushInfo("Step 3/3: Relating original network to D8 network…")

    # Build a temporary in-memory layer from routed8_features for relate_networks()
    # relate_networks() expects a QgsVectorLayer, not a feature list
    route_fields = QgsFields()
    route_fields.append(QgsField(rid_field, QMetaType.LongLong))
    route_fields.append(QgsField("ORIG_FID", QMetaType.LongLong))

    crs = routes.sourceCrs()
    routed8_layer = QgsVectorLayer(
        f"LineString?crs={crs.authid()}", "routed8_tmp", "memory"
    )
    pr = routed8_layer.dataProvider()
    pr.addAttributes(route_fields)
    routed8_layer.updateFields()
    pr.addFeatures(routed8_features)

    relate_rows = relate_networks(
        shapefile_a=routes,
        rid_a=rid_field,
        shapefile_b=routed8_layer,
        rid_b=rid_field,
        feedback=feedback,
        strict_count=False,
    )

    # Fix ORIG_FID on routeD8 features using relate table
    # relate_rows is list of (rid_a, rid_b, part_count) where rid_a=routes, rid_b=routesD8
    rid_b_to_rid_a = {int(rb): int(ra) for ra, rb, _ in relate_rows}

    fixed_features = []
    for feat in routed8_features:
        d8_rid = int(feat[rid_field])
        orig = rid_b_to_rid_a.get(d8_rid, -999)
        new_f = QgsFeature(feat)
        new_f.setAttribute("ORIG_FID", orig)
        fixed_features.append(new_f)
    routed8_features = fixed_features

    return routed8_features, linksd8_rows, ptsond8_rows, relate_rows


def execute_order_reaches(
    routes,
    links,
    rid_field,
    r_flowacc,
    routeD8,
    linksD8,
    ptsonD8,
    relatetable,
    outputfield,
    feedback=None,
):
    """
    Orchestrates the full Order Reaches workflow.

    Mirrors ArcGIS execute_OrderReaches() in LargeScaleFloodMetaTools.py.

    Steps:
        1. locate_most_downstream_points() — find the most downstream point
           on each D8 reach from pathpointsD8
        2. Sample flow accumulation raster at those points using GDAL
        3. Join back through fd_net_relatetable to get routes_main RIDs
        4. locate_points_along_routes() — compute MEAS of each point along
           its corresponding routes_main reach
        5. order_tree_by_flowacc() — traverse routes_main downstream→upstream,
           prioritizing highest flow accumulation at confluences, assign Qorder
        6. Return updated routes_main features with Qorder field added

    Args:
        routes      : QgsVectorLayer (lines) — routes_main
        links       : QgsFeatureSource — routes_main_links
        rid_field   : str — RouteID field name
        r_flowacc   : QgsRasterLayer — flow accumulation raster
        routeD8     : QgsVectorLayer (lines) — routesD8
        linksD8     : QgsFeatureSource — linksD8
        ptsonD8     : QgsFeatureSource — pathpointsD8
        relatetable : QgsFeatureSource — fd_net_relatetable
        outputfield : str — name of the output field (e.g. "Qorder")
        feedback    : QgsProcessingFeedback or None

    Returns:
        list of QgsFeature (lines) — routes_main features with outputfield added
    """
    from osgeo import gdal
    import numpy as np
    from qgis.core import (
        QgsVectorLayer,
        QgsFeature,
        QgsFields,
        QgsField,
        QgsWkbTypes,
        QgsGeometry,
        QgsPointXY,
    )
    from qgis.PyQt.QtCore import QMetaType
    from modeling.LocateMostDownstreamPoints import locate_most_downstream_points
    from modeling.LocatePointsAlongRoutes import locate_points_along_routes
    from tree_qgis.RiverNetwork import RiverNetwork, PointsCollection, DataPoint

    # -------------------------------------------------------------------------
    # Step 1: Find most downstream point on each D8 reach
    # -------------------------------------------------------------------------
    if feedback:
        feedback.pushInfo("Step 1/5: Locating most downstream points on D8 network…")

    downstream_pts = locate_most_downstream_points(
        network_shp=routeD8,
        links_table=linksD8,
        rid_field=rid_field,
        datapoints=ptsonD8,
        id_field_pts="id",
        rid_field_pts="RID",
        distance_field_pts="dist",
        x_field_pts="X",
        y_field_pts="Y",
        feedback=feedback,
    )

    # -------------------------------------------------------------------------
    # Step 2: Sample flow accumulation raster at downstream points
    # -------------------------------------------------------------------------
    if feedback:
        feedback.pushInfo("Step 2/5: Sampling flow accumulation raster…")

    path = r_flowacc.source()
    ds   = gdal.Open(path, gdal.GA_ReadOnly)
    if ds is None:
        raise Exception(f"GDAL could not open flow accumulation raster: {path}")

    facc_array = ds.GetRasterBand(1).ReadAsArray()
    gt         = ds.GetGeoTransform()
    xmin       = gt[0]
    ymax       = gt[3]
    pixel_w    = abs(gt[1])
    pixel_h    = abs(gt[5])
    height, width = facc_array.shape
    ds = None

    def _sample_flowacc(x, y):
        col = int((x - xmin) / pixel_w)
        row = int((ymax - y) / pixel_h)
        if 0 <= row < height and 0 <= col < width:
            return float(facc_array[row, col])
        return None

    # Build a memory layer of downstream points with flowacc values
    # and their ptsonD8 id — needed for the join through relate table
    # First build a lookup: point id -> (x, y) from downstream_pts
    pt_id_to_xy = {}
    for f in downstream_pts:
        geom = f.geometry()
        if geom is None or geom.isEmpty():
            continue
        pt   = geom.asPoint()
        pt_id_to_xy[int(f["id"])] = (pt.x(), pt.y())

    # Build lookup: ptsonD8 id -> RID (D8)
    ptid_to_d8rid = {}
    for f in ptsonD8.getFeatures():
        ptid_to_d8rid[int(f["id"])] = int(f["RID"])

    # Build relate table lookup: D8 RID -> routes_main RID
    # fd_net_relatetable has fields RID (routes_main) and RID_1 (routesD8)
    d8rid_to_mainrid = {}
    for f in relatetable.getFeatures():
        main_rid = f["RID"]
        d8_rid   = f["RID_1"]
        if main_rid is not None and d8_rid is not None:
            d8rid_to_mainrid[int(d8_rid)] = int(main_rid)

    # -------------------------------------------------------------------------
    # Step 3: Build QpointsMain — points with flowacc, keyed to routes_main RID
    # -------------------------------------------------------------------------
    if feedback:
        feedback.pushInfo("Step 3/5: Joining flow accumulation to routes_main RIDs…")

    # QpointsMain: list of (pt_id, main_rid, flowacc, x, y)
    qpoints_main_rows = []
    for pt_id, (x, y) in pt_id_to_xy.items():
        flowacc = _sample_flowacc(x, y)
        if flowacc is None:
            if feedback:
                feedback.pushWarning(
                    f"Point id={pt_id} at ({x:.1f},{y:.1f}) is outside "
                    f"the flow accumulation raster — skipping."
                )
            continue

        d8_rid   = ptid_to_d8rid.get(pt_id)
        if d8_rid is None:
            continue

        main_rid = d8rid_to_mainrid.get(d8_rid)
        if main_rid is None:
            if feedback:
                feedback.pushWarning(
                    f"D8 RID={d8_rid} has no match in fd_net_relatetable — skipping."
                )
            continue

        qpoints_main_rows.append((pt_id, main_rid, flowacc, x, y))

    # -------------------------------------------------------------------------
    # Step 4: Locate QpointsMain along routes_main
    # -------------------------------------------------------------------------
    if feedback:
        feedback.pushInfo("Step 4/5: Locating points along routes_main…")

    # Build a temporary memory layer for QpointsMain (needed by
    # locate_points_along_routes which expects a QgsFeatureSource)
    qpts_fields = QgsFields()
    qpts_fields.append(QgsField("id",      QMetaType.LongLong))
    qpts_fields.append(QgsField("RID",     QMetaType.LongLong))
    qpts_fields.append(QgsField("flowacc", QMetaType.Double))

    crs = routes.sourceCrs()
    qpts_layer = QgsVectorLayer(
        f"Point?crs={crs.authid()}", "qpts_main_tmp", "memory"
    )
    pr = qpts_layer.dataProvider()
    pr.addAttributes(qpts_fields)
    qpts_layer.updateFields()

    qpts_feats = []
    for pt_id, main_rid, flowacc, x, y in qpoints_main_rows:
        f = QgsFeature(qpts_fields)
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
        f.setAttributes([pt_id, main_rid, flowacc])
        qpts_feats.append(f)
    pr.addFeatures(qpts_feats)

    located_rows = locate_points_along_routes(
        points=qpts_layer,
        points_rid_field="RID",
        routes=routes,
        routes_rid_field=rid_field,
        distance=10000.0,
        feedback=feedback,
    )

    # -------------------------------------------------------------------------
    # Step 5: Order tree by flow accumulation
    # -------------------------------------------------------------------------
    if feedback:
        feedback.pushInfo("Step 5/5: Ordering reaches by flow accumulation…")

    # Build a PointsCollection from located_rows for RiverNetwork
    # located_rows fields: id, RID, MEAS
    # We also need flowacc — build a lookup from pt_id -> flowacc
    ptid_to_flowacc = {
        pt_id: flowacc
        for pt_id, main_rid, flowacc, x, y in qpoints_main_rows
    }

    # Build a temporary memory layer with id, RID, MEAS, flowacc
    # for loading into PointsCollection
    meas_fields = QgsFields()
    meas_fields.append(QgsField("id",      QMetaType.LongLong))
    meas_fields.append(QgsField("RID",     QMetaType.LongLong))
    meas_fields.append(QgsField("MEAS",    QMetaType.Double))
    meas_fields.append(QgsField("flowacc", QMetaType.Double))

    meas_layer = QgsVectorLayer(
        f"None?crs={crs.authid()}", "meas_tmp", "memory"
    )
    pr2 = meas_layer.dataProvider()
    pr2.addAttributes(meas_fields)
    meas_layer.updateFields()

    meas_feats = []
    for located_feat in located_rows:
        pt_id   = int(located_feat["id"])
        rid     = int(located_feat["RID"])
        meas    = float(located_feat["MEAS"])
        flowacc = ptid_to_flowacc.get(pt_id, 0.0)

        f = QgsFeature(meas_fields)
        f.setAttributes([pt_id, rid, meas, flowacc])
        meas_feats.append(f)
    pr2.addFeatures(meas_feats)

    # Load into RiverNetwork and order
    network = RiverNetwork()
    network.load_data(routes, links, rid_field=rid_field)

    collection = PointsCollection(network, "flowacc")
    collection.dict_attr_fields["id"]       = "id"
    collection.dict_attr_fields["reach_id"] = "RID"
    collection.dict_attr_fields["dist"]     = "MEAS"
    collection.dict_attr_fields["flowacc"]  = "flowacc"
    collection.load_table(meas_layer)

    network.order_reaches_by_discharge(collection, "flowacc")

    # -------------------------------------------------------------------------
    # Build output features — routes_main with outputfield added
    # -------------------------------------------------------------------------
    out_fields = QgsFields(routes.fields())
    if out_fields.indexOf(outputfield) == -1:
        out_fields.append(QgsField(outputfield, QMetaType.LongLong))

    qorder_idx = out_fields.indexOf(outputfield)

    out_features = []
    for f in routes.getFeatures():
        rid   = int(f[rid_field])
        reach = network.get_reach(rid)
        order = int(reach.order) if reach and reach.order is not None else -999

        new_f = QgsFeature(out_fields)
        new_f.setGeometry(f.geometry())
        # Copy all original attributes
        for field in routes.fields():
            new_f.setAttribute(field.name(), f[field.name()])
        new_f.setAttribute(outputfield, order)
        out_features.append(new_f)

    if feedback:
        feedback.pushInfo(
            f"Order reaches complete. {len(out_features)} reach(es) ordered."
        )

    return out_features