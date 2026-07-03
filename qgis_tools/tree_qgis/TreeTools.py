import math
import numpy as np
from osgeo import gdal
from collections import defaultdict
from qgis.PyQt.QtCore import QMetaType
from qgis.core import (
    QgsFeature,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsPointXY,
    QgsSpatialIndex,
    QgsVectorLayer,
)

# =============================================================================
# Helpers
# =============================================================================

def _reverse_line_geometry(geom: QgsGeometry) -> QgsGeometry:
    """
    Reverse vertex order of a line geometry.

    Used to ensure all reaches are oriented consistently
    from downstream to upstream.
    """
    if geom is None or geom.isEmpty():
        return geom

    if geom.isMultipart():
        parts = geom.asMultiPolyline()
        rev_parts = [list(reversed(pl)) for pl in parts]
        return QgsGeometry.fromMultiPolylineXY(rev_parts)

    pl = geom.asPolyline()
    return QgsGeometry.fromPolylineXY(list(reversed(pl)))


def _last_vertex_first_part(geom: QgsGeometry):
    """
    Return the first vertex of the first part of a line geometry as QgsPointXY.
    Reaches are oriented upstream→downstream, so the first vertex is the upstream end.
    Returns None if geometry is invalid or empty.
    """
    if geom is None or geom.isEmpty():
        return None
    if geom.isMultipart():
        parts = geom.asMultiPolyline()
        if not parts or not parts[0]:
            return None
        return QgsPointXY(parts[0][-1])
    line = geom.asPolyline()
    if not line:
        return None
    return QgsPointXY(line[-1])

# =============================================================================
# Raster
# =============================================================================

class FlowDirRaster:
    """
    Loads a D8 flow direction raster into a numpy array via GDAL for fast pixel access.
    D8 encoding (ArcGIS / WhiteboxTools D8Pointer):
        1=E, 2=SE, 4=S, 8=SW, 16=W, 32=NW, 64=N, 128=NE
    """
    VALID_DIRS = {1, 2, 4, 8, 16, 32, 64, 128}

    D8_STEPS = {
        1: (0, 1),  # E
        2: (1, 1),  # SE
        4: (1, 0),  # S
        8: (1, -1),  # SW
        16: (0, -1),  # W
        32: (-1, -1),  # NW
        64: (-1, 0),  # N
        128: (-1, 1),  # NE
    }

    def __init__(self, r_flow_dir):
        """
        Args:
            r_flow_dir: QgsRasterLayer — flow direction raster (already validated by wrapper)
        """
        path = r_flow_dir.source()
        ds = gdal.Open(path, gdal.GA_ReadOnly)
        if ds is None:
            raise ValueError(f"GDAL could not open flow direction raster: {path}")

        self.array = ds.GetRasterBand(1).ReadAsArray()  # full raster into numpy array
        self.height, self.width = self.array.shape

        gt = ds.GetGeoTransform()
        # gt: (xmin, pixel_w, 0, ymax, 0, -pixel_h)
        self.xmin   = gt[0]
        self.ymax   = gt[3]
        self.pixel_w = abs(gt[1])
        self.pixel_h = abs(gt[5])

        ds = None  # close file handle

    def x_to_col(self, x):
        return int((x - self.xmin) / self.pixel_w)

    def y_to_row(self, y):
        return int((self.ymax - y) / self.pixel_h)

    def col_to_x(self, col):
        return self.xmin + (col + 0.5) * self.pixel_w

    def row_to_y(self, row):
        return self.ymax - (row + 0.5) * self.pixel_h

    def in_bounds(self, row, col):
        return (0 <= row < self.height) and (0 <= col < self.width)

    def get_value(self, row, col):
        return (int(self.array[row, col]))

    def step(self, row, col):
        """
        Return (new_row, new_col, distance) after one D8 step,
        or None if the current cell has no valid direction.
        """
        direction = self.get_value(row, col)
        if direction not in self.VALID_DIRS:
            return None

        dr, dc = self.D8_STEPS[direction]
        new_row = row + dr
        new_col = col + dc

        if dr != 0 and dc != 0:
            dist = math.sqrt(self.pixel_w ** 2 + self.pixel_h ** 2)
        elif dc != 0:
            dist = self.pixel_w
        else:
            dist = self.pixel_h

        return new_row, new_col, dist

# =============================================================================
# Core functions
# =============================================================================

def create_network_from_fc(rivernet, rid_field, downstream_field, channeltype_field, feedback=None, coord_round_digits=1):

    if feedback:
        feedback.pushInfo("Building endpoint index…")

    rid_to_endpoints = defaultdict(list)
    node_to_endpoints = defaultdict(list)
    rid_to_features = defaultdict(list)

    def node_key(pt):
        return (round(pt.x(), coord_round_digits), round(pt.y(), coord_round_digits))

    total = rivernet.featureCount() if rivernet is not None else 0

    for i, f in enumerate(rivernet.getFeatures()):
        if feedback and feedback.isCanceled():
            break
        if feedback and total:
            feedback.setProgress(int(100 * i / max(1, total)))

        rid_val = f[rid_field]
        if rid_val is None:
            continue

        geom = f.geometry()
        if geom is None or geom.isEmpty():
            continue

        if geom.isMultipart():
            parts = geom.asMultiPolyline()
            if not parts or not parts[0]:
                continue
            line = parts[0]
        else:
            line = geom.asPolyline()
            if not line:
                continue

        start_pt = QgsPointXY(line[0])
        end_pt   = QgsPointXY(line[-1])

        downflag = f[downstream_field]
        channel  = f[channeltype_field] if channeltype_field else None

        start_node = node_key(start_pt)
        end_node   = node_key(end_pt)

        e_start = {"RID": rid_val, "ENDTYPE": "Start", "NODE": start_node, "CHANNEL": channel, "DOWN": downflag}
        e_end   = {"RID": rid_val, "ENDTYPE": "End",   "NODE": end_node,   "CHANNEL": channel, "DOWN": downflag}

        rid_to_endpoints[rid_val].extend([e_start, e_end])
        node_to_endpoints[start_node].append(e_start)
        node_to_endpoints[end_node].append(e_end)
        rid_to_features[rid_val].append(f)

    if not rid_to_features:
        raise Exception("No valid line features found (check RID field and geometry).")

    # Find the downstream reach
    down_rids = []
    for rid, eps in rid_to_endpoints.items():
        for ep in eps:
            if ep["DOWN"] in (1, True, "1"):
                down_rids.append(rid)
                break

    if not down_rids:
        raise Exception(
            "No downstream reach found. "
            "Check DownEnd field values (should contain 1)."
        )

    if feedback:
        feedback.pushInfo(f"Found {len(down_rids)} downstream reach(es). Resolving outlet endpoint…")

    # Auto-detect reversed line orientation
    # Lines should have START vertex at the downstream end (outlet) and END vertex at the upstream end (headwaters).
    # If the outlet is at the START vertex instead, lines are reversed and need to be flipped.
    needs_flip = False
    for rid in down_rids:
        eps = rid_to_endpoints[rid]
        outlet_ep = None
        for ep in eps:
            others = [e for e in node_to_endpoints[ep["NODE"]] if e["RID"] != rid]
            if len(others) == 0:
                outlet_ep = ep
                break

        if outlet_ep is None:
            eps_sorted = sorted(
                eps,
                key=lambda e: len([x for x in node_to_endpoints[e["NODE"]] if x["RID"] != rid])
            )
            outlet_ep = eps_sorted[0]

        # Check orientation: outlet should be at START (downstream vertex), not END
        if outlet_ep["ENDTYPE"] == "End":
            needs_flip = True
            if feedback:
                feedback.pushWarning(
                    f"Detected reversed line orientation (RID {rid} outlet is at End vertex). "
                    f"Flipping all lines automatically."
                )
            break

    # If lines are reversed, flip them all and rebuild the endpoint index
    if needs_flip:
        # Reverse all geometries
        for rid in rid_to_features.keys():
            for i, feat in enumerate(rid_to_features[rid]):
                new_feat = QgsFeature(feat)
                new_feat.setGeometry(_reverse_line_geometry(feat.geometry()))
                rid_to_features[rid][i] = new_feat

        # Rebuild endpoint index with reversed geometries
        rid_to_endpoints.clear()
        node_to_endpoints.clear()
        for rid, feats in rid_to_features.items():
            for f in feats:
                geom = f.geometry()
                if geom.isMultipart():
                    parts = geom.asMultiPolyline()
                    if not parts or not parts[0]:
                        continue
                    line = parts[0]
                else:
                    line = geom.asPolyline()
                    if not line:
                        continue
                start_pt = QgsPointXY(line[0])
                end_pt = QgsPointXY(line[-1])
                downflag = f[downstream_field]
                channel = f[channeltype_field] if channeltype_field else None
                start_node = node_key(start_pt)
                end_node = node_key(end_pt)
                e_start = {"RID": rid, "ENDTYPE": "Start", "NODE": start_node, "CHANNEL": channel, "DOWN": downflag}
                e_end = {"RID": rid, "ENDTYPE": "End", "NODE": end_node, "CHANNEL": channel, "DOWN": downflag}
                rid_to_endpoints[rid].extend([e_start, e_end])
                node_to_endpoints[start_node].append(e_start)
                node_to_endpoints[end_node].append(e_end)

    # For each downstream reach, find the endpoint that connects to NO other reach —
    # that is the true outlet end, regardless of digitizing direction.
    downstream_endpoints = []
    for rid in down_rids:
        eps = rid_to_endpoints[rid]
        outlet_ep = None
        for ep in eps:
            others = [e for e in node_to_endpoints[ep["NODE"]] if e["RID"] != rid]
            if len(others) == 0:
                # This end touches nothing else — it's the outlet
                outlet_ep = ep
                break
        if outlet_ep is None:
            # Fallback: use whichever endpoint has fewest connections
            eps_sorted = sorted(
                eps,
                key=lambda e: len([x for x in node_to_endpoints[e["NODE"]] if x["RID"] != rid])
            )
            outlet_ep = eps_sorted[0]
            if feedback:
                feedback.pushWarning(
                    f"Could not find isolated outlet endpoint for RID={rid}, "
                    f"using endpoint with fewest connections."
                )
        downstream_endpoints.append(outlet_ep)

    if feedback:
        feedback.pushInfo(f"Outlet endpoint(s) resolved. Building links…")

    links_rows  = []
    flip_rids   = set()
    reaches_done = set()

    def get_other_endpoint(rid, endpoint):
        eps = rid_to_endpoints.get(rid, [])
        if len(eps) < 2:
            return None
        for e in eps:
            if not (e["NODE"] == endpoint["NODE"] and e["ENDTYPE"] == endpoint["ENDTYPE"]):
                return e
        return None

    def sort_candidates(cands):
        if channeltype_field:
            return sorted(cands, key=lambda d: (d["CHANNEL"] is None, d["CHANNEL"]))
        return cands

    def recurse(down_ep):
        rid = down_ep["RID"]

        # Orientation: downstream point = first vertex (Start)
        # Find tributary reaches whose Start vertex (their outlet) connects
        # to this reach's upstream endpoint

        reaches_done.add(rid)

        up_ep = get_other_endpoint(rid, down_ep)
        if up_ep is None:
            return

        # Find tributaries whose start vertex (outlet) connects to current reaches upstream endpoint
        connected = [e for e in node_to_endpoints[up_ep["NODE"]]
                     if e["RID"] != rid and e["ENDTYPE"] == "Start"]
        connected = sort_candidates(connected)

        for cand in connected:
            up_rid = cand["RID"]
            if channeltype_field and down_ep["CHANNEL"] == 0 and cand["CHANNEL"] == 1:
                continue
            if up_rid in reaches_done:
                continue
            links_rows.append((rid, up_rid))
            recurse(cand)

    for dep in downstream_endpoints:
        if feedback and feedback.isCanceled():
            break
        if dep["RID"] not in reaches_done:
            recurse(dep)

    if feedback:
        feedback.pushInfo(f"Links created: {len(links_rows)}. Flipping {len(flip_rids)} reach(es)…")

    out_features = []
    for rid, feats in rid_to_features.items():
        for in_f in feats:
            new_f = QgsFeature(in_f)
            if rid in flip_rids:
                new_f.setGeometry(_reverse_line_geometry(in_f.geometry()))
            out_features.append(new_f)

    # --- Enforce downstream→upstream orientation on all output features ---
    # Anchor: the outlet node of the downstream reach is known.
    # Walk upstream from there and flip any reach whose orientation doesn't match.

    up_to_down = {up: down for down, up in links_rows}

    rid_to_out_idx = {}
    for idx, f in enumerate(out_features):
        rid_to_out_idx[int(f[rid_field])] = idx

    def get_line(feat):
        g = feat.geometry()
        if g.isMultipart():
            parts = g.asMultiPolyline()
            return parts[0] if parts else []
        return g.asPolyline()

    # First fix the downstream reach — its FIRST vertex must be the outlet node
    for dep in downstream_endpoints:
        rid = dep["RID"]
        if rid not in rid_to_out_idx:
            continue
        feat = out_features[rid_to_out_idx[rid]]
        line = get_line(feat)
        if not line:
            continue
        first_key = node_key(QgsPointXY(line[0]))
        if first_key != dep["NODE"]:
            new_f = QgsFeature(feat)
            new_f.setGeometry(_reverse_line_geometry(feat.geometry()))
            out_features[rid_to_out_idx[rid]] = new_f

    # Now fix all upstream reaches — each reach's FIRST vertex (downstream/outlet)
    # must match the LAST vertex of its downstream neighbour (confluence)
    for up_rid, down_rid in up_to_down.items():
        if up_rid not in rid_to_out_idx or down_rid not in rid_to_out_idx:
            continue
        up_feat = out_features[rid_to_out_idx[up_rid]]
        down_feat = out_features[rid_to_out_idx[down_rid]]
        up_line = get_line(up_feat)
        down_line = get_line(down_feat)
        if not up_line or not down_line:
            continue
        # Upstream reach Start vertex (outlet) must match downstream reach End vertex (upstream limit)
        down_last_key = node_key(QgsPointXY(down_line[-1]))
        up_first_key = node_key(QgsPointXY(up_line[0]))
        if up_first_key != down_last_key:
            new_f = QgsFeature(up_feat)
            new_f.setGeometry(_reverse_line_geometry(up_feat.geometry()))
            out_features[rid_to_out_idx[up_rid]] = new_f

    def _add_m_values(feat):
        """Add M values to a line feature, M=0 at first vertex increasing upstream."""
        from qgis.core import QgsLineString, QgsPoint
        g = feat.geometry()
        if g.isMultipart():
            parts = g.asMultiPolyline()
            line = parts[0] if parts else []
        else:
            line = g.asPolyline()
        if not line:
            return feat
        m = 0.0
        points = []
        for i, pt in enumerate(line):
            if i > 0:
                prev = line[i - 1]
                m += ((pt.x() - prev.x()) ** 2 + (pt.y() - prev.y()) ** 2) ** 0.5
            points.append(QgsPoint(pt.x(), pt.y(), m=m))
        new_geom = QgsGeometry(QgsLineString(points))
        new_f = QgsFeature(feat)
        new_f.setGeometry(new_geom)
        return new_f

    out_features = [_add_m_values(f) for f in out_features]

    return out_features, links_rows


def create_from_points_and_splits(routes, links, rid_field, links_up_field="UpID", links_down_field="DownID", feedback=None):
    """
    Classify each reach's upstream endpoint as a from-point (headwater) or
    split-point (single upstream neighbour), for use as seeds in tree_from_flowdir().

    Args:
        routes        : QgsVectorLayer (lines) — oriented route network
        links         : QgsVectorLayer or QgsFeatureSource — DownID/UpID link table
        rid_field     : str — name of the RouteID field in routes
        links_up_field: str — name of the upstream RID field in links table (default "UpID")
        links_down_field: str — name of the downstream RID field in links table (default "DownID")
        feedback      : QgsProcessingFeedback or None

    Returns:
        fp_features    : list of QgsFeature (Point) — headwater upstream endpoints, with RID attribute
        split_features : list of QgsFeature (Point) — single-upstream-neighbour endpoints, no attributes
    """

    if feedback:
        feedback.pushInfo("Building upstream count from link table…")

    # Count how many upstream reaches flow into each reach
    upstream_count = defaultdict(int)
    for row in links.getFeatures():
        down_id = row[links_down_field]
        if down_id is None:
            continue
        upstream_count[down_id] += 1

    # Collect all reach IDs from the route layer
    all_rids = set()
    for f in routes.getFeatures():
        rid = f[rid_field]
        if rid is not None:
            all_rids.add(rid)

    headwaters  = {rid for rid in all_rids if upstream_count.get(rid, 0) == 0}
    one_upstream = {rid for rid in all_rids if upstream_count.get(rid, 0) == 1}

    if feedback:
        feedback.pushInfo(
            f"Found {len(headwaters)} headwater reach(es) and "
            f"{len(one_upstream)} single-upstream reach(es)."
        )

    # Build output QgsFields for from-points (needs RID); split-points carry no attributes
    fp_fields = QgsFields()
    fp_fields.append(QgsField(rid_field, QMetaType.LongLong))

    fp_features    = []
    split_features = []

    total = routes.featureCount()
    for i, reach in enumerate(routes.getFeatures()):
        if feedback and feedback.isCanceled():
            break
        if feedback and total:
            feedback.setProgress(int(100 * i / max(1, total)))

        rid = reach[rid_field]
        if rid is None:
            continue

        pt = _last_vertex_first_part(reach.geometry())
        if pt is None:
            continue

        if rid in headwaters:
            feat = QgsFeature(fp_fields)
            feat.setGeometry(QgsGeometry.fromPointXY(pt))
            feat.setAttribute(rid_field, int(rid))
            fp_features.append(feat)

        elif rid in one_upstream:
            feat = QgsFeature()
            feat.setGeometry(QgsGeometry.fromPointXY(pt))
            split_features.append(feat)

    if feedback:
        feedback.pushInfo(
            f"Created {len(fp_features)} from-point(s) and "
            f"{len(split_features)} split-point(s)."
        )

    return fp_features, split_features


def tree_from_flowdir(
    r_flow_dir,
    fp_features,
    split_features,
    rid_field,
    crs,
    tolerance=10000,
    feedback=None,
):
    """
    Trace D8 flow paths from headwater from-points, building a routed
    line network, link table, and points-on-path table.

    Mirrors ArcGIS execute_TreeFromFlowDir() but accepts QgsFeature lists
    and returns data for the Processing wrapper to sink.

    Args:
        r_flow_dir     : QgsRasterLayer — D8 flow direction raster
        fp_features    : list of QgsFeature (Point) — headwater seeds with RID attribute
                         (from create_from_points_and_splits)
        split_features : list of QgsFeature (Point) — split-point seeds, no attributes
                         (from create_from_points_and_splits)
        rid_field      : str — name of the RID attribute in fp_features
        crs            : QgsCoordinateReferenceSystem — from routes layer
        tolerance      : float — max snap distance for split points (default 10000,
                         matches ArcGIS original)
        feedback       : QgsProcessingFeedback or None

    Returns:
        route_features : list of QgsFeature (LineString) with fields [RID, RID_routesmain]
        links_rows     : list of (downRID, upRID)
        points_rows    : list of (id, RID, dist, offset, X, Y, row, col)
    """

    def warn(msg):
        if feedback:
            feedback.pushWarning(msg)
        else:
            print(f"WARNING: {msg}")

    # --- Load raster ---
    if feedback:
        feedback.pushInfo("Loading flow direction raster…")
    flowdir = FlowDirRaster(r_flow_dir)

    # --- State ---
    segmentid   = 0
    pointid     = 0
    loop_error  = False

    links        = []   # list of (downRID, upRID)
    points       = []   # list of dicts: {id, RID, dist, offset, X, Y, row, col}
    cell_index   = {}   # (row, col) -> index into points (first occurrence)
    rid_to_indices = {} # RID -> [indices into points]
    initialpoint = {}   # RID -> QgsPointXY (downstream start vertex)
    original_fp  = {}   # RID -> original from-point RID attribute

    # --- Helpers ---
    def add_points_batch(pointslist, totaldist, rid):
        """Reverse dist (was measured upstream→downstream), append to global points."""
        idxs = rid_to_indices.setdefault(rid, [])
        for rec in pointslist:
            new_rec = {
                "id":     rec[0],
                "RID":    rid,
                "dist":   float(totaldist - rec[2]),
                "offset": 0.0,
                "X":      float(rec[4]),
                "Y":      float(rec[5]),
                "row":    int(rec[6]),
                "col":    int(rec[7]),
            }
            idx = len(points)
            points.append(new_rec)
            idxs.append(idx)
            cell_index.setdefault((new_rec["row"], new_rec["col"]), idx)

    def reassign_upstream_part(old_rid, split_dist, new_rid):
        """
        Move all points with dist > split_dist from old_rid to new_rid.
        Shift their dist values relative to the split point.
        Returns number of points moved.
        """
        old_idxs = rid_to_indices.get(old_rid, [])
        keep, moved = [], []
        for idx in old_idxs:
            if points[idx]["dist"] > split_dist:
                points[idx]["RID"]  = new_rid
                points[idx]["dist"] = float(points[idx]["dist"] - split_dist)
                moved.append(idx)
            else:
                keep.append(idx)
        rid_to_indices[old_rid]  = keep
        rid_to_indices[new_rid]  = rid_to_indices.get(new_rid, []) + moved
        return len(moved)

    def update_links_downstream(old_down, new_down):
        """Rename all occurrences of old_down in the downstream slot of the links table."""
        for i, (d, u) in enumerate(links):
            if d == old_down:
                links[i] = (new_down, u)

    # --- Trace from each from-point ---
    if feedback:
        feedback.pushInfo(f"Tracing {len(fp_features)} from-point(s)…")

    total = len(fp_features)
    for fp_idx, fp_feat in enumerate(fp_features):
        if feedback and feedback.isCanceled():
            break
        if feedback and total:
            feedback.setProgress(int(50 * fp_idx / max(1, total)))

        geom = fp_feat.geometry()
        if geom is None or geom.isEmpty():
            continue

        pt       = geom.asPoint()
        fp_rid   = int(fp_feat[rid_field])

        currentcol = flowdir.x_to_col(pt.x())
        currentrow = flowdir.y_to_row(pt.y())

        # Validate starting cell
        intheraster = True
        if not flowdir.in_bounds(currentrow, currentcol):
            intheraster = False
        elif flowdir.get_value(currentrow, currentcol) not in FlowDirRaster.VALID_DIRS:
            intheraster = False

        if (currentrow, currentcol) in cell_index:
            intheraster = False
            warn(f"From point RID={fp_rid} already on flow path")

        if not intheraster:
            continue

        segmentid += 1
        rid = segmentid
        totaldist = 0.0
        pointslist = []
        coords_in_path = set()

        # --- Walk downstream pixel by pixel ---
        while intheraster:
            if len(pointslist) < 5:
                feedback.pushInfo(
                    f"  Step {len(pointslist)}: row={currentrow} col={currentcol} "
                    f"val={flowdir.get_value(currentrow, currentcol)}"
                )
            pointid += 1
            x = flowdir.col_to_x(currentcol)
            y = flowdir.row_to_y(currentrow)
            pointslist.append([
                pointid, rid, totaldist, 0.0,
                x, y, currentrow, currentcol
            ])
            coords_in_path.add((currentrow, currentcol))

            result = flowdir.step(currentrow, currentcol)
            if result is None:
                intheraster = False
                break

            next_row, next_col, step_dist = result

            # Bounds check on destination cell
            if not flowdir.in_bounds(next_row, next_col):
                intheraster = False
                break
            if flowdir.get_value(next_row, next_col) not in FlowDirRaster.VALID_DIRS:
                intheraster = False
                break

            totaldist += step_dist

            # Loop check within this path
            if (next_row, next_col) in coords_in_path:
                intheraster = False
                warn(
                    f"Infinite loop found at "
                    f"{flowdir.col_to_x(next_col):.4f};"
                    f"{flowdir.row_to_y(next_row):.4f}"
                )
                add_points_batch(pointslist, totaldist, rid)
                break

            # Confluence check — hits a previously traced path
            if (next_row, next_col) in cell_index:
                conf_idx  = cell_index[(next_row, next_col)]
                conf      = points[conf_idx]
                conf_rid  = int(conf["RID"])
                conf_dist = float(conf["dist"])
                conf_x    = float(conf["X"])
                conf_y    = float(conf["Y"])

                new_up_rid = segmentid + 1
                moved = reassign_upstream_part(conf_rid, conf_dist, new_up_rid)

                if moved > 0:
                    update_links_downstream(conf_rid, new_up_rid)
                    add_points_batch(pointslist, totaldist, rid)
                    links.append((conf_rid, rid))
                    links.append((conf_rid, new_up_rid))
                    initialpoint[rid] = QgsPointXY(conf_x, conf_y)
                    initialpoint[new_up_rid] = QgsPointXY(conf_x, conf_y)
                    original_fp[rid] = fp_rid
                    if conf_rid in original_fp:
                        original_fp[new_up_rid] = original_fp.pop(conf_rid)
                    segmentid = new_up_rid
                else:
                    warn(f"Reach {rid} encountered another from-point (met at start)")
                    add_points_batch(pointslist, totaldist, rid)  # ADD THIS BACK
                    links.append((conf_rid, rid))
                    original_fp[rid] = fp_rid
                    initialpoint[rid] = QgsPointXY(conf_x, conf_y)

                intheraster = False
                break

            currentrow, currentcol = next_row, next_col

        # Normal path termination
        if not loop_error and pointslist and rid not in original_fp:
            add_points_batch(pointslist, totaldist, rid)
            original_fp[rid] = fp_rid

    # --- Apply split points ---
    if split_features:
        if feedback:
            feedback.pushInfo(f"Applying {len(split_features)} split-point(s)…")

        # Build a spatial index over accumulated flow points for snap matching
        flow_pt_layer = QgsVectorLayer(
            f"Point?crs={crs.authid()}", "flow_pts_tmp", "memory"
        )
        pr = flow_pt_layer.dataProvider()
        pr.addAttributes([
            QgsField("pt_idx", QMetaType.LongLong),
            QgsField(rid_field, QMetaType.LongLong),
            QgsField("dist",    QMetaType.Double),
            QgsField("X",       QMetaType.Double),
            QgsField("Y",       QMetaType.Double),
        ])
        flow_pt_layer.updateFields()

        tmp_feats = []
        for idx, rec in enumerate(points):
            f = QgsFeature(flow_pt_layer.fields())
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(rec["X"], rec["Y"])))
            f.setAttributes([idx, rec["RID"], rec["dist"], rec["X"], rec["Y"]])
            tmp_feats.append(f)
        pr.addFeatures(tmp_feats)

        sp_index   = QgsSpatialIndex(flow_pt_layer.getFeatures())
        id_to_feat = {f.id(): f for f in flow_pt_layer.getFeatures()}

        used_flow_ids = set()
        matches       = []

        for sp_feat in split_features:
            g = sp_feat.geometry()
            if g is None or g.isEmpty():
                continue
            sp_pt  = QgsPointXY(g.asPoint())
            nearest = sp_index.nearestNeighbor(sp_pt, 1)
            if not nearest:
                continue

            flow_feat = id_to_feat[nearest[0]]
            flow_id   = flow_feat.id()
            if flow_id in used_flow_ids:
                continue

            dist_to = flow_feat.geometry().distance(
                QgsGeometry.fromPointXY(sp_pt)
            )
            if tolerance is not None and dist_to > tolerance:
                continue

            used_flow_ids.add(flow_id)
            matches.append((
                int(flow_feat[rid_field]),
                float(flow_feat["dist"]),
                float(flow_feat["X"]),
                float(flow_feat["Y"]),
            ))

        # Process largest dist first (upstream→downstream), matching ArcGIS sort
        matches.sort(key=lambda t: t[1], reverse=True)

        for rid_old, split_dist, sx, sy in matches:
            segmentid += 1
            rid_new    = segmentid

            moved = reassign_upstream_part(rid_old, split_dist, rid_new)
            if moved <= 0:
                continue

            update_links_downstream(rid_old, rid_new)
            links.append((rid_old, rid_new))
            initialpoint[rid_new] = QgsPointXY(sx, sy)

            if rid_old in original_fp:
                original_fp[rid_new] = original_fp.pop(rid_old)

    # --- Build route features ---
    if feedback:
        feedback.pushInfo("Building route geometries…")

    route_fields = QgsFields()
    route_fields.append(QgsField(rid_field, QMetaType.LongLong))
    route_fields.append(QgsField("RID_routesmain", QMetaType.LongLong))

    route_features = []
    for rid in sorted(rid_to_indices.keys()):
        idxs = rid_to_indices[rid]
        if not idxs:
            continue

        pts_sorted = sorted(
            [points[i] for i in idxs],
            key=lambda p: p["dist"]
        )

        geom_pts = []
        if rid in initialpoint:
            p0 = initialpoint[rid]
            geom_pts.append(QgsPointXY(p0.x(), p0.y()))

        for rec in pts_sorted:
            geom_pts.append(QgsPointXY(rec["X"], rec["Y"]))

        if len(geom_pts) < 2:
            continue

        feat = QgsFeature(route_fields)
        feat.setGeometry(QgsGeometry.fromPolylineXY(geom_pts))
        feat.setAttribute(rid_field, int(rid))
        feat.setAttribute("RID_routesmain", int(original_fp.get(rid, -999)))
        route_features.append(feat)

    # --- Pack points rows ---
    points_rows = [
        (p["id"], p["RID"], p["dist"], p["offset"],
         p["X"], p["Y"], p["row"], p["col"])
        for p in points
    ]

    if feedback:
        feedback.pushInfo(
            f"Done. {len(route_features)} route(s), "
            f"{len(links)} link(s), "
            f"{len(points_rows)} flow point(s)."
        )

    return route_features, links, points_rows

def place_points_at_regular_interval(routes, links, rid_field, interval, feedback=None):
    """
    Places points at a regular interval along each reach in the network.
    Mirrors ArcGIS placePointsAtRegularInterval.

    Parameters
    ----------
    routes    : QgsVectorLayer - oriented route network (lines)
    links     : QgsVectorLayer - DownID/UpID link table
    rid_field : str - name of the RID field
    interval  : float - distance between points in metres
    feedback  : QgsProcessingFeedback or None

    Returns
    -------
    list of (id, rid, meas) tuples
    """
    import numpy as np

    # Build reaches dict: rid -> (length, geometry)
    reaches = {}
    for feat in routes.getFeatures():
        rid = int(feat[rid_field])
        length = feat.geometry().length()
        reaches[rid] = {'length': length, 'geometry': feat.geometry()}

    # Build links: rid -> downstream rid, rid -> list of upstream rids
    downstream = {}  # rid -> down_rid
    upstream = {}    # rid -> [up_rids]
    for feat in links.getFeatures():
        down_id = int(feat['DownID'])
        up_id   = int(feat['UpID'])
        downstream[up_id] = down_id
        upstream.setdefault(down_id, []).append(up_id)

    all_rids = set(reaches.keys())

    # Find downstream ends — rids not present in UpID
    up_ids = set(downstream.keys())
    downstream_ends = all_rids - set(downstream.keys())

    # Browse reaches downstream to upstream recursively
    def browse_down_to_up(rid):
        yield rid
        for up_rid in upstream.get(rid, []):
            yield from browse_down_to_up(up_rid)

    # Place points
    point_id = 0
    rows = []  # (id, rid, meas)

    for end_rid in downstream_ends:
        for rid in browse_down_to_up(end_rid):
            length = reaches[rid]['length']
            for dist in np.arange(0, length, interval):
                rows.append((point_id, rid, float(dist)))
                point_id += 1

    if feedback:
        feedback.pushInfo(f"Placed {len(rows)} points across {len(reaches)} reach(es).")

    return rows