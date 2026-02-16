from collections import defaultdict
from qgis.core import QgsFeature, QgsGeometry, QgsPointXY


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


def create_network_from_fc(
    rivernet,
    rid_field,
    downstream_field,
    channeltype_field,
    feedback=None,
    coord_round_digits=6
):
    """
    Build a river network topology from a line feature class.

    Returns:
        out_features : features with corrected orientation
        links_rows   : list of (DownRID, UpRID)
    """

    # Progress message
    if feedback:
        feedback.pushInfo("Building endpoint index…")

    # RID to its 2 endpoints
    rid_to_endpoints = defaultdict(list)
    # Node (rounded coordinate) to all endpoints that touch it
    node_to_endpoints = defaultdict(list)
    # RID to original input features (for flipped copy outputs)
    rid_to_features = defaultdict(list)

    def node_key(pt: QgsPointXY) -> tuple:
        """
        Create a coordinate key with rounding to avoid
        floating-point precision mismatches at junctions.
        """
        return (round(pt.x(), coord_round_digits), round(pt.y(), coord_round_digits))

    total = rivernet.featureCount() if rivernet is not None else 0

    # Index each reach by its start and end node
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

        # Use first part if multipart
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

        # Store both endpoints of this reach
        e_start = {"RID": rid_val, "ENDTYPE": "Start", "NODE": start_node, "CHANNEL": channel, "DOWN": downflag}
        e_end = {"RID": rid_val, "ENDTYPE": "End", "NODE": end_node, "CHANNEL": channel, "DOWN": downflag}

        rid_to_endpoints[rid_val].extend([e_start, e_end])
        node_to_endpoints[start_node].append(e_start)
        node_to_endpoints[end_node].append(e_end)
        rid_to_features[rid_val].append(f)

    if not rid_to_features:
        raise Exception("No valid line features found (check RID field and geometry).")

    # Identify the most downstream reaches (only one node touches or DownEnd = 1)
    downstream_endpoints = []
    for node, eps in node_to_endpoints.items():
        if len(eps) == 1:
            ep = eps[0]
            if ep["DOWN"] in (1, True, "1"):
                downstream_endpoints.append(ep)

    if not downstream_endpoints:
        raise Exception(
            "No downstream endpoints found. "
            "Check DownEnd field values (should contain 1) and ensure endpoints connect."
        )

    if feedback:
        feedback.pushInfo(f"Found {len(downstream_endpoints)} downstream start point(s). Building links…")

    # Output structures
    links_rows = []
    flip_rids = set()
    reaches_done = set()

    def get_other_endpoint(rid, endpoint):
        """Return the opposite endpoint of a reach."""
        eps = rid_to_endpoints.get(rid, [])
        if len(eps) < 2:
            return None
        for e in eps:
            if not (e["NODE"] == endpoint["NODE"] and e["ENDTYPE"] == endpoint["ENDTYPE"]):
                return e
        return None

    def sort_candidates(cands):
        """
        If a channel type exists:
        process secondary channels before main channels.
        """
        if channeltype_field:
            return sorted(cands, key=lambda d: (d["CHANNEL"] is None, d["CHANNEL"]))
        return cands

    def recurse(down_ep):
        """
        Recursive upstream traversal.

        Builds:
        - DownRID to UpRID link table
        - list of reaches that need flipping
        """
        rid = down_ep["RID"]

        # If downstream junction is the "end" of the line, geometry is reversed and must be flipped
        if down_ep["ENDTYPE"] == "End":
            flip_rids.add(rid)

        reaches_done.add(rid)

        # Move to the upstream node of this reach
        up_ep = get_other_endpoint(rid, down_ep)
        if up_ep is None:
            return

        # All other reaches connected to that node
        connected = [e for e in node_to_endpoints[up_ep["NODE"]] if e["RID"] != rid]
        connected = sort_candidates(connected)

        for cand in connected:
            up_rid = cand["RID"]

            # Prevent recursion from a secondary into a main channel
            if channeltype_field and down_ep["CHANNEL"] == 0 and cand["CHANNEL"] == 1:
                continue

            if up_rid in reaches_done:
                continue

            links_rows.append((rid, up_rid))
            recurse(cand)

    # Build the network by traversing upstream from downstream reaches
    for dep in downstream_endpoints:
        if feedback and feedback.isCanceled():
            break
        if dep["RID"] not in reaches_done:
            recurse(dep)

    if feedback:
        feedback.pushInfo(f"Links created: {len(links_rows)}. Flipping {len(flip_rids)} reach(es) if needed…")

    # Output features with corrected orientation
    out_features = []
    for rid, feats in rid_to_features.items():
        for in_f in feats:
            new_f = QgsFeature(in_f)
            if rid in flip_rids:
                new_f.setGeometry(_reverse_line_geometry(in_f.geometry()))
            out_features.append(new_f)

    return out_features, links_rows