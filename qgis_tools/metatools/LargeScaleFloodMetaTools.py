from pathlib import Path
import sys
import csv

sys.path.append(str(Path(__file__).resolve().parents[1]))

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
    route_fields.append(QgsField("RID_routesmain", QMetaType.LongLong))

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
        new_f.setAttribute("RID_routesmain", orig)
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


def spatialize_q_from_gauging_stations(
        flow_acc,
        routes_d8,
        rid_field_d8,
        links_d8,
        d8_pathpoints,
        q_stations,
        id_field_q,
        name_field_q,
        drainage_field_q,
        q_distance=None,
        csv_file=None,
        dem_footprints=None,
        dem_id_field=None,
        beta=1.0,
        feedback=None,
        rid_field_q=None,
        dist_field_q=None,
        q_field=None,
):
    """
    Spatializes discharge from gauging stations across the D8 network.

    Uses drainage area power law: Q = Q_station x (A/A_station)^beta

    Mirrors ArcGIS execute_SpatializeQ_from_gauging_stations. Two modes,
    selected by whether q_field is None (matching ArcGIS's
    "if Q_field is None" branching):

    - q_field is None (LiDAR discharges): q_stations are located on the
      D8 network internally via nearest-route search (q_distance), and
      discharges come from a multi-day CSV (csv_file) keyed by
      dem_footprints/dem_id_field per pathpoint. Original behavior,
      unchanged.

    - q_field is not None (flood discharges): q_stations are expected to
      already carry RID (rid_field_q) and MEAS (dist_field_q) — e.g. from
      a prior Locate Stations Along Routes run — and the discharge value
      is read directly from q_field on each station. csv_file,
      dem_footprints, dem_id_field, q_distance are ignored in this mode.

    Args:
        flow_acc         : QgsRasterLayer  - flow accumulation raster
        routes_d8        : QgsVectorLayer  - D8 routes (lines)
        rid_field_d8     : str             - RID field in routes
        links_d8         : QgsVectorLayer  - DownID/UpID link table
        d8_pathpoints    : QgsVectorLayer  - points along D8 routes (table with X, Y)
        q_stations       : QgsVectorLayer  - gauging station points
        id_field_q       : str             - ID field in stations
        name_field_q     : str             - name field (must match CSV headers, LiDAR mode)
        drainage_field_q : str             - drainage area field (km2)
        q_distance       : float or None   - max snap distance to river (m) — LiDAR mode only
        csv_file         : str or None     - path to CSV with discharges — LiDAR mode only
        dem_footprints   : QgsVectorLayer or None - DEM footprint polygons — LiDAR mode only
        dem_id_field     : str or None     - ID_DEM field in footprints — LiDAR mode only
        beta             : float           - drainage area exponent
        feedback         : QgsProcessingFeedback
        rid_field_q      : str or None     - RID field already on q_stations — flood mode only
        dist_field_q     : str or None     - MEAS field already on q_stations — flood mode only
        q_field          : str or None     - discharge field already on q_stations — flood mode only.
                            When set, switches to flood mode.

    Returns:
        list of dicts - pathpoints with computed discharge
    """
    from qgis.core import QgsSpatialIndex, QgsVectorLayer, QgsFeature, QgsFields, QgsField
    from qgis.PyQt.QtCore import QMetaType
    from tree_qgis.RiverNetwork import RiverNetwork, PointsCollection, DataPoint

    # -------------------------------------------------------------------------
    # Step 1: Extract flow accumulation to D8 pathpoints
    # -------------------------------------------------------------------------
    feedback.pushInfo("Step 1: Extracting flow accumulation to D8 pathpoints...")

    ds      = gdal.Open(flow_acc.source())
    gt      = ds.GetGeoTransform()
    band    = ds.GetRasterBand(1)
    nodata  = band.GetNoDataValue()
    cell_width  = abs(gt[1])
    cell_height = abs(gt[5])

    d8_pts_data = []
    for feat in d8_pathpoints.getFeatures():
        if feedback.isCanceled():
            break
        d = {}
        for f in d8_pathpoints.fields().names():
            d[f] = feat[f]

        if "X" in d and "Y" in d and d["X"] is not None and d["Y"] is not None:
            x   = float(d["X"])
            y   = float(d["Y"])
            col = int((x - gt[0]) / gt[1])
            row = int((y - gt[3]) / gt[5])
            if 0 <= col < ds.RasterXSize and 0 <= row < ds.RasterYSize:
                val = band.ReadAsArray(col, row, 1, 1)
                if val is not None:
                    pixel_val    = float(val[0][0])
                    d["flowacc"] = None if (nodata is not None and pixel_val == nodata) else pixel_val
                else:
                    d["flowacc"] = None
            else:
                d["flowacc"] = None
        else:
            d["flowacc"] = None

        d8_pts_data.append(d)

    ds = None
    feedback.pushInfo(f"  Loaded {len(d8_pts_data)} D8 pathpoints")

    if q_field is None:
        # =========================================================================
        # LiDAR discharge mode — original behavior, unchanged
        # =========================================================================

        # -------------------------------------------------------------------------
        # Step 2: Spatial join pathpoints with DEM footprints to get ID_DEM
        # -------------------------------------------------------------------------
        feedback.pushInfo("Step 2/6: Assigning DEM IDs to pathpoints...")

        dem_feats = list(dem_footprints.getFeatures())
        for pt in d8_pts_data:
            if feedback.isCanceled():
                break
            if "X" in pt and "Y" in pt:
                test_geom      = QgsGeometry.fromPointXY(QgsPointXY(float(pt["X"]), float(pt["Y"])))
                pt[dem_id_field] = None
                for dem_feat in dem_feats:
                    if dem_feat.geometry().contains(test_geom) or dem_feat.geometry().distance(test_geom) == 0.0:
                        pt[dem_id_field] = dem_feat[dem_id_field]
                        break

        # -------------------------------------------------------------------------
        # Step 3: Locate gauging stations along D8 routes to get RID and MEAS
        #         Equivalent to ArcGIS LocateFeaturesAlongRoutes_lr
        # -------------------------------------------------------------------------
        feedback.pushInfo("Step 3/6: Locating gauging stations along D8 routes...")

        route_index = QgsSpatialIndex()
        route_feats = {}
        for feat in routes_d8.getFeatures():
            route_index.insertFeature(feat)
            route_feats[feat.id()] = feat

        q_stations_data = []
        for feat in q_stations.getFeatures():
            if feedback.isCanceled():
                break

            pt_geom = feat.geometry()
            if pt_geom is None or pt_geom.isEmpty():
                continue

            search_rect = pt_geom.boundingBox()
            search_rect.grow(q_distance)
            candidate_ids = route_index.intersects(search_rect)

            best_rid  = None
            best_meas = None
            best_dist = float("inf")

            for fid in candidate_ids:
                route_feat = route_feats[fid]
                route_geom = route_feat.geometry()
                nearest    = route_geom.nearestPoint(pt_geom)
                snap_dist  = nearest.distance(pt_geom)

                if snap_dist <= q_distance and snap_dist < best_dist:
                    best_dist = snap_dist
                    best_rid  = int(route_feat[rid_field_d8])
                    best_meas = route_geom.lineLocatePoint(pt_geom)

            if best_rid is None:
                feedback.pushWarning(
                    f"  Station '{feat[name_field_q]}' (id={feat[id_field_q]}) "
                    f"is more than {q_distance}m from any D8 route — skipping."
                )
                continue

            q_stations_data.append({
                "id":            feat[id_field_q],
                "name":          feat[name_field_q],
                "drainage_area": float(feat[drainage_field_q]),
                "RID":           best_rid,
                "dist":          best_meas,
            })

        feedback.pushInfo(f"  Located {len(q_stations_data)} gauging station(s) on D8 routes")

        # -------------------------------------------------------------------------
        # Step 4: Read discharge CSV
        # -------------------------------------------------------------------------
        feedback.pushInfo("Step 4/6: Reading discharge CSV...")

        q_dict = {}
        with open(csv_file, 'r') as csvfile:
            csvreader     = csv.DictReader(csvfile)
            station_names = csvreader.fieldnames[1:]
            for station in station_names:
                q_dict[station] = {}
            first_col = csvreader.fieldnames[0]
            for line in csvreader:
                id_dem = line[first_col]
                for station in station_names:
                    try:
                        q_dict[station][id_dem] = float(line[station])
                    except (ValueError, KeyError):
                        q_dict[station][id_dem] = None

        feedback.pushInfo(
            f"  Read discharges for {len(q_dict)} station(s) "
            f"across {len(q_dict[station_names[0]])} DEM day(s)"
        )

        for station in q_stations_data:
            station_name = station["name"]
            if station_name not in q_dict:
                feedback.pushWarning(f"  Station '{station_name}' not found in CSV — skipping.")
                station["discharges"] = {}
            else:
                station["discharges"] = q_dict[station_name]

    else:
        # =========================================================================
        # Flood discharge mode — mirrors ArcGIS's "else" branch:
        # Qpts.discharges = {Q_field: Qpts.discharge}; targetpt.DEM = Q_field
        # q_stations must already carry RID (rid_field_q) and MEAS (dist_field_q),
        # e.g. from a prior Locate Stations Along Routes run.
        # =========================================================================
        feedback.pushInfo(f"Reading gauging station data for scenario '{q_field}'...")

        q_stations_data = []
        for feat in q_stations.getFeatures():
            if feedback.isCanceled():
                break
            rid = feat[rid_field_q]
            if rid is None:
                feedback.pushWarning(
                    f"  Station '{feat[name_field_q]}' has no RID — skipping."
                )
                continue
            q_val = feat[q_field]
            if q_val is None:
                feedback.pushWarning(
                    f"  Station '{feat[name_field_q]}' has no discharge value — skipping."
                )
                continue

            q_stations_data.append({
                "id":            feat[id_field_q],
                "name":          feat[name_field_q],
                "drainage_area": float(feat[drainage_field_q]),
                "RID":           int(rid),
                "dist":          float(feat[dist_field_q]),
                "discharges":    {q_field: float(q_val)},
            })

        feedback.pushInfo(f"  Loaded {len(q_stations_data)} gauging station(s)")
        dem_id_field = "DEM"  # constant field name; value on every target point is q_field

    # -------------------------------------------------------------------------
    # Step 5: Build RiverNetwork and PointsCollections
    #         Mirrors ArcGIS: network.load_data / Qcollection / targetcollection
    # -------------------------------------------------------------------------
    feedback.pushInfo("Building river network and loading points...")

    network = RiverNetwork()
    network.load_data(routes_d8, links_d8, rid_field=rid_field_d8)

    # --- Build Qcollection (gauging stations) ---
    q_fields = QgsFields()
    q_fields.append(QgsField("id",            QMetaType.LongLong))
    q_fields.append(QgsField("RID",           QMetaType.LongLong))
    q_fields.append(QgsField("dist",          QMetaType.Double))
    q_fields.append(QgsField("name",          QMetaType.QString))
    q_fields.append(QgsField("drainage_area", QMetaType.Double))

    q_layer = QgsVectorLayer(
        f"None?crs={routes_d8.sourceCrs().authid()}", "qstations_tmp", "memory"
    )
    pr = q_layer.dataProvider()
    pr.addAttributes(q_fields)
    q_layer.updateFields()

    q_feats = []
    for i, st in enumerate(q_stations_data):
        f = QgsFeature(q_fields)
        f.setAttributes([i + 1, st["RID"], st["dist"], st["name"], st["drainage_area"]])
        q_feats.append(f)
    pr.addFeatures(q_feats)

    Qcollection = PointsCollection(network, "Qpts")
    Qcollection.dict_attr_fields["id"] = "id"
    Qcollection.dict_attr_fields["reach_id"] = "RID"
    Qcollection.dict_attr_fields["dist"] = "dist"
    Qcollection.load_table(q_layer)

    station_by_id = {i + 1: st for i, st in enumerate(q_stations_data)}
    for pt in Qcollection._points.values():
        st = station_by_id.get(pt.id)
        if st:
            pt.name = st["name"]
            pt.drainage_area = st["drainage_area"]
            if q_field is not None:
                pt.discharges = st["discharges"]

    if q_field is None:
        # Assign discharge dictionaries to Qcollection points (LiDAR mode)
        station_discharges = {st["name"]: st["discharges"] for st in q_stations_data}
        for reach in network.browse_reaches_down_to_up():
            for qpt in reach.browse_points(Qcollection, orientation="DOWN_TO_UP"):
                name = qpt.name
                if name in station_discharges:
                    qpt.discharges = station_discharges[name]
                else:
                    feedback.pushWarning(f"  Station '{name}' has no discharges assigned.")
                    qpt.discharges = {}

    # --- Build targetcollection (D8 pathpoints) ---
    t_fields = QgsFields()
    t_fields.append(QgsField("id",        QMetaType.LongLong))
    t_fields.append(QgsField("RID",       QMetaType.LongLong))
    t_fields.append(QgsField("dist",      QMetaType.Double))
    t_fields.append(QgsField("flowacc",   QMetaType.Double))
    t_fields.append(QgsField(dem_id_field, QMetaType.QString))

    t_layer = QgsVectorLayer(
        f"None?crs={routes_d8.sourceCrs().authid()}", "targetpts_tmp", "memory"
    )
    pr2 = t_layer.dataProvider()
    pr2.addAttributes(t_fields)
    t_layer.updateFields()

    t_feats = []
    for i, pt in enumerate(d8_pts_data):
        rid = pt.get(rid_field_d8)
        if rid is None:
            continue
        f = QgsFeature(t_fields)
        f.setAttributes([
            i + 1,
            int(rid),
            float(pt.get("dist", 0.0) or 0.0),
            float(pt["flowacc"]) if pt.get("flowacc") is not None else None,
            q_field if q_field is not None else pt.get(dem_id_field),
        ])
        t_feats.append(f)
    pr2.addFeatures(t_feats)

    targetcollection = PointsCollection(network, "target")
    targetcollection.dict_attr_fields["id"] = "id"
    targetcollection.dict_attr_fields["reach_id"] = "RID"
    targetcollection.dict_attr_fields["dist"] = "dist"
    targetcollection.dict_attr_fields["flowacc"] = "flowacc"
    targetcollection.load_table(t_layer)

    if q_field is None:
        pt_dem_by_id = {i + 1: pt.get(dem_id_field) for i, pt in enumerate(d8_pts_data) if pt.get(rid_field_d8) is not None}
        for pt in targetcollection._points.values():
            pt.DEM = pt_dem_by_id.get(pt.id)
    else:
        for pt in targetcollection._points.values():
            pt.DEM = q_field

    # -------------------------------------------------------------------------
    # Step 6: Compute discharges — mirrors ArcGIS execute_SpatializeQ_from_gauging_stations
    # -------------------------------------------------------------------------
    feedback.pushInfo("Computing discharges...")

    result_points = _compute_discharges(
        network=network,
        Qcollection=Qcollection,
        targetcollection=targetcollection,
        dem_id_field=dem_id_field,
        beta=beta,
        cell_width=cell_width,
        cell_height=cell_height,
        d8_pts_data=d8_pts_data,
        feedback=feedback,
    )

    feedback.pushInfo(f"Done. Computed discharges for {len(result_points)} point(s).")
    return result_points

def _compute_discharges(
        network,
        Qcollection,
        targetcollection,
        dem_id_field,
        beta,

        cell_width,
        cell_height,
        d8_pts_data,
        feedback,
):
    """
    Core discharge computation using RiverNetwork traversal.

    Mirrors ArcGIS execute_SpatializeQ_from_gauging_stations browse logic exactly:
    - First browse (up_to_down):  assign upstream Q station(s) to each target point
    - Second browse (down_to_up): assign downstream Q station, compute discharge,
                                  propagate upstream_calculated_Q reach by reach

    Returns list of dicts (original d8_pts_data entries) with 'computedQ' added.
    """

    class RefPoint:
        """Mirrors ArcGIS Ref_point class."""
        def __init__(self, name, discharges, drainage_area, reach, dist):
            self.name          = name
            self.discharges    = discharges
            self.drainage_area = drainage_area
            self.reach         = reach
            self.dist          = dist

    # --- First browse: assign upstream Q station(s) to each target point ---
    # Mirrors ArcGIS first browse (browse_reaches_up_to_down)

    for reach in network.browse_reaches_down_to_up():
        for targetpt in reach.browse_points(targetcollection, orientation="DOWN_TO_UP"):
            targetpt.upQpts = []

    lastQpts = None
    for reach in network.browse_reaches_up_to_down():
        if reach.is_upstream_end():
            lastQpts = None

        for Qpts in reach.browse_points(Qcollection, orientation="UP_TO_DOWN"):
            if lastQpts is not None:
                max_dist = lastQpts.dist if lastQpts.reach.id == reach.id else None
                for targetpt in reach.browse_points(targetcollection, orientation="UP_TO_DOWN"):
                    if (max_dist is None or targetpt.dist <= max_dist) and targetpt.dist > Qpts.dist:
                        if lastQpts.name not in [pt.name for pt in targetpt.upQpts]:
                            targetpt.upQpts.append(lastQpts)
            lastQpts = RefPoint(
                Qpts.name, Qpts.discharges, Qpts.drainage_area, Qpts.reach, Qpts.dist
            )

        if lastQpts is not None:
            max_dist = lastQpts.dist if lastQpts.reach.id == reach.id else None
            for targetpt in reach.browse_points(targetcollection, orientation="UP_TO_DOWN"):
                if max_dist is None or targetpt.dist <= max_dist:
                    if lastQpts.name not in [pt.name for pt in targetpt.upQpts]:
                        targetpt.upQpts.append(lastQpts)

    # --- Second browse: assign downstream Q station and compute discharges ---
    # Mirrors ArcGIS second browse (browse_reaches_down_to_up)

    for reach in network.browse_reaches_down_to_up():
        if feedback and feedback.isCanceled():
            break

        ### Block 1: find closest downstream Q point ###

        lastQpts = None
        if not reach.is_downstream_end():
            down_reach = reach.get_downstream_reach()
            if hasattr(down_reach, "upstream_calculated_Q"):
                lastQpts = down_reach.upstream_calculated_Q

        for Qpts in reach.browse_points(Qcollection, orientation="DOWN_TO_UP"):
            if lastQpts is not None:
                min_dist = lastQpts.dist if lastQpts.reach.id == reach.id else 0
                for targetpt in reach.browse_points(targetcollection, orientation="DOWN_TO_UP"):
                    if targetpt.dist >= min_dist:
                        targetpt.downQpts = lastQpts
            lastQpts = RefPoint(
                Qpts.name, Qpts.discharges, Qpts.drainage_area, Qpts.reach, Qpts.dist
            )

        if lastQpts is not None:
            min_dist = lastQpts.dist if lastQpts.reach.id == reach.id else 0
            for targetpt in reach.browse_points(targetcollection, orientation="DOWN_TO_UP"):
                if targetpt.dist >= min_dist:
                    targetpt.downQpts = lastQpts

        ### Block 2: compute discharges ###

        for targetpt in reach.browse_points(targetcollection, orientation="DOWN_TO_UP"):

            if targetpt.flowacc is None:
                targetpt.computedQ = -999
                continue
            local_area = targetpt.flowacc * cell_width * cell_height / 1_000_000  # km2

            # interpolatedQ is now local to each target point — keyed by station name
            interpolatedQ = {}

            if not hasattr(targetpt, "downQpts"):
                # No downstream point — simple proportionality from upstream
                for uppt in targetpt.upQpts:
                    interpolatedQ[uppt.name] = {
                        k: uppt.discharges.get(k, -999) * (local_area / uppt.drainage_area) ** beta
                        if uppt.discharges.get(k) is not None and uppt.drainage_area > 0
                        else -999
                        for k in uppt.discharges
                    }
            else:
                # Linear interpolation of A^beta between upstream and downstream stations
                down = targetpt.downQpts
                for uppt in targetpt.upQpts:
                    denom = down.drainage_area ** beta - uppt.drainage_area ** beta
                    q_from_down = {}
                    q_from_up   = {}

                    # Get all discharge keys from both stations
                    all_keys = set(down.discharges.keys()) | set(uppt.discharges.keys())

                    for k in all_keys:
                        down_q = down.discharges.get(k)
                        up_q   = uppt.discharges.get(k)

                        if down_q is not None and denom != 0:
                            factor = (local_area ** beta - uppt.drainage_area ** beta) / denom
                            q_from_down[k] = factor * down_q
                        else:
                            q_from_down[k] = -999

                        if up_q is not None and denom != 0:
                            factor = (down.drainage_area ** beta - local_area ** beta) / denom
                            q_from_up[k] = factor * up_q
                        else:
                            q_from_up[k] = -999

                    interpolatedQ[uppt.name] = {
                        k: q_from_down.get(k, -999) + q_from_up.get(k, -999)
                        for k in all_keys
                    }

            # Weight results by upstream station drainage area
            if len(targetpt.upQpts) > 0:
                total_weight = sum(s.drainage_area for s in targetpt.upQpts)
                # Get all discharge keys across all upstream stations
                all_keys = set()
                for uppt in targetpt.upQpts:
                    all_keys |= set(uppt.discharges.keys())

                targetpt.weightedQ = {}
                for k in all_keys:
                    weighted_sum = 0.0
                    for uppt in targetpt.upQpts:
                        q_val = interpolatedQ.get(uppt.name, {}).get(k, -999)
                        if q_val != -999 and total_weight > 0:
                            weighted_sum += q_val * uppt.drainage_area / total_weight
                        else:
                            weighted_sum = -999
                            break
                    targetpt.weightedQ[k] = weighted_sum
            else:
                # No upstream points — use downstream station only
                if hasattr(targetpt, "downQpts"):
                    down = targetpt.downQpts
                    if down.drainage_area > 0:
                        targetpt.weightedQ = {
                            k: down.discharges.get(k, -999) * (local_area / down.drainage_area) ** beta
                            if down.discharges.get(k) is not None
                            else -999
                            for k in down.discharges
                        }
                    else:
                        targetpt.weightedQ = {}
                else:
                    targetpt.weightedQ = {}

            # Extract discharge for this point's DEM day
            dem_key = getattr(targetpt, "DEM", None)
            if hasattr(targetpt, "weightedQ") and dem_key in targetpt.weightedQ:
                targetpt.computedQ = targetpt.weightedQ[dem_key]
            else:
                targetpt.computedQ = -999

        ### Block 3: convert last upstream point into Q input for upstream reaches ###
        # Mirrors ArcGIS: reach.upstream_calculated_Q = Ref_point(...)

        last_pt = reach.get_last_point(targetcollection)
        if last_pt is not None and hasattr(last_pt, "weightedQ"):
            reach.upstream_calculated_Q = RefPoint(
                name          = f"uppt_reach{reach.id}",
                discharges    = last_pt.weightedQ,
                drainage_area = last_pt.flowacc * cell_width * cell_height / 1_000_000,
                reach         = reach,
                dist          = last_pt.dist,
            )

    # --- Map computed discharges back to original d8_pts_data dicts ---
    # targetcollection points are indexed 1..N matching d8_pts_data order
    pt_id_to_computed = {}
    for pt in targetcollection._points.values():
        pt_id_to_computed[pt.id] = getattr(pt, "computedQ", -999)

    for i, pt in enumerate(d8_pts_data):
        pt_id = i + 1  # matches the id assigned during load
        pt["computedQ"] = pt_id_to_computed.get(pt_id, -999)

    return d8_pts_data