from __future__ import annotations

from collections import Counter, defaultdict
import math
from typing import Any, Iterable

from .RiverNetwork import PointsCollection, RiverNetwork
from .geometry import Coordinate, FlowPathPoint, FullTopologyLink, LineFeature, PointFeature, TopologyLink, ensure_line_feature, ensure_links, ensure_point_feature
from .interfaces import FeedbackProtocol, FlowDirectionRasterProtocol


def _info(feedback: FeedbackProtocol | None, message: str) -> None:
    if feedback is not None and hasattr(feedback, "pushInfo"):
        feedback.pushInfo(message)


def _warn(feedback: FeedbackProtocol | None, message: str) -> None:
    if feedback is not None and hasattr(feedback, "pushWarning"):
        feedback.pushWarning(message)


def _is_canceled(feedback: FeedbackProtocol | None) -> bool:
    return bool(feedback is not None and hasattr(feedback, "isCanceled") and feedback.isCanceled())


def _set_progress(feedback: FeedbackProtocol | None, progress: int) -> None:
    if feedback is not None and hasattr(feedback, "setProgress"):
        feedback.setProgress(progress)


def create_network_from_features(
    rivernet: Iterable[LineFeature | dict[str, Any]],
    rid_field: str,
    downstream_field: str,
    channeltype_field: str | None = None,
    feedback: FeedbackProtocol | None = None,
    coord_round_digits: int = 1,
) -> tuple[list[LineFeature], list[TopologyLink]]:
    features = [ensure_line_feature(feature) for feature in rivernet]
    rid_to_feature: dict[int, LineFeature] = {}
    rid_to_endpoints: dict[int, list[dict[str, Any]]] = defaultdict(list)
    node_to_endpoints: dict[tuple[float, float], list[dict[str, Any]]] = defaultdict(list)

    def node_key(point: Coordinate) -> tuple[float, float]:
        return (round(point.x, coord_round_digits), round(point.y, coord_round_digits))

    _info(feedback, "Building endpoint index…")
    total = len(features)
    for index, feature in enumerate(features):
        if _is_canceled(feedback):
            break
        if total:
            _set_progress(feedback, int(100 * index / max(1, total)))
        rid = int(feature.attributes[rid_field])
        rid_to_feature[rid] = feature
        start_node = node_key(feature.start_point)
        end_node = node_key(feature.end_point)
        channel_value = feature.attributes.get(channeltype_field) if channeltype_field else None
        down_flag = feature.attributes.get(downstream_field)
        start_endpoint = {
            rid_field: rid,
            "RID": rid,
            "ENDTYPE": "Start",
            "NODE": start_node,
            "CHANNEL": channel_value,
            "DOWN": down_flag,
        }
        end_endpoint = {
            rid_field: rid,
            "RID": rid,
            "ENDTYPE": "End",
            "NODE": end_node,
            "CHANNEL": channel_value,
            "DOWN": down_flag,
        }
        rid_to_endpoints[rid].extend([start_endpoint, end_endpoint])
        node_to_endpoints[start_node].append(start_endpoint)
        node_to_endpoints[end_node].append(end_endpoint)

    if not rid_to_feature:
        raise RuntimeError("No valid line features found.")

    downstream_junctions = []
    for endpoints in rid_to_endpoints.values():
        for endpoint in endpoints:
            isolated = len(node_to_endpoints[endpoint["NODE"]]) == 1
            downstream_flag = endpoint["DOWN"] in (1, True, "1")
            if isolated and downstream_flag:
                downstream_junctions.append(endpoint)

    if not downstream_junctions:
        raise RuntimeError("No downstream reach found. Check downstream field values.")

    _info(feedback, "Tracing topology and line orientation…")
    flipped_reaches: set[int] = set()
    links: list[TopologyLink] = []
    reaches_done: list[int] = []

    def other_endpoint(endpoint: dict[str, Any]) -> dict[str, Any]:
        for candidate in rid_to_endpoints[int(endpoint["RID"])]:
            if candidate["ENDTYPE"] != endpoint["ENDTYPE"]:
                return candidate
        raise RuntimeError(f"Reach {endpoint['RID']} does not have two endpoints.")

    def recurse(downstream_junction: dict[str, Any]) -> None:
        rid = int(downstream_junction["RID"])
        if downstream_junction["ENDTYPE"] == "End":
            flipped_reaches.add(rid)
        reaches_done.append(rid)
        current_upstream_junction = other_endpoint(downstream_junction)
        other_upstream_junctions = [
            endpoint
            for endpoint in node_to_endpoints[current_upstream_junction["NODE"]]
            if int(endpoint["RID"]) != rid
        ]
        if channeltype_field is not None:
            other_upstream_junctions.sort(key=lambda endpoint: endpoint["CHANNEL"])
        for upstream_junction in other_upstream_junctions:
            up_rid = int(upstream_junction["RID"])
            allowed = (
                channeltype_field is None
                or not (
                    downstream_junction["CHANNEL"] == 0
                    and upstream_junction["CHANNEL"] == 1
                )
            )
            if allowed and up_rid not in reaches_done:
                links.append(TopologyLink(rid, up_rid))
                recurse(upstream_junction)

    for endpoint in downstream_junctions:
        rid = int(endpoint["RID"])
        if rid not in reaches_done:
            recurse(endpoint)

    out_features = []
    for rid, feature in rid_to_feature.items():
        current_feature = feature.reversed() if rid in flipped_reaches else feature
        out_features.append(current_feature.with_m_values())
    return out_features, links


def create_network_from_fc(
    rivernet: Iterable[LineFeature | dict[str, Any]],
    rid_field: str,
    downstream_field: str,
    channeltype_field: str | None,
    feedback: FeedbackProtocol | None = None,
    coord_round_digits: int = 1,
):
    return create_network_from_features(
        rivernet,
        rid_field,
        downstream_field,
        channeltype_field=channeltype_field,
        feedback=feedback,
        coord_round_digits=coord_round_digits,
    )


def create_full_tree_table_from_features(
    route_features: Iterable[LineFeature | dict[str, Any]],
    route_id_field: str,
    id_link_1_name: str = "RID1",
    id_link_2_name: str = "RID2",
    orientation_name: str = "Orientation",
    coord_round_digits: int = 6,
) -> list[FullTopologyLink]:
    features = [ensure_line_feature(feature) for feature in route_features]
    rid_to_endpoints: dict[int, list[dict[str, Any]]] = defaultdict(list)
    node_to_endpoints: dict[tuple[float, float], list[dict[str, Any]]] = defaultdict(list)

    def node_key(point: Coordinate) -> tuple[float, float]:
        return (round(point.x, coord_round_digits), round(point.y, coord_round_digits))

    for feature in features:
        rid = int(feature.attributes[route_id_field])
        start = {"RID": rid, "ENDTYPE": "Start", "NODE": node_key(feature.start_point)}
        end = {"RID": rid, "ENDTYPE": "End", "NODE": node_key(feature.end_point)}
        rid_to_endpoints[rid].extend([start, end])
        node_to_endpoints[start["NODE"]].append(start)
        node_to_endpoints[end["NODE"]].append(end)

    links: list[FullTopologyLink] = []

    def link_exists(first: int, second: int, orientation: str) -> bool:
        reverse_checks = {
            "END-TO-START": ("START-TO-END",),
            "START-TO-END": ("END-TO-START",),
            "END-TO-END": ("END-TO-END",),
            "START-TO-START": ("START-TO-START",),
        }
        for link in links:
            if (
                link.reach_id_1 == first
                and link.reach_id_2 == second
                and link.orientation == orientation
            ):
                return True
            if (
                link.reach_id_1 == second
                and link.reach_id_2 == first
                and link.orientation in reverse_checks[orientation]
            ):
                return True
        return False

    for rid, endpoints in rid_to_endpoints.items():
        for endpoint in endpoints:
            for other in node_to_endpoints[endpoint["NODE"]]:
                if other["RID"] == rid:
                    continue
                if endpoint["ENDTYPE"] == "End":
                    orientation = "END-TO-START" if other["ENDTYPE"] == "Start" else "END-TO-END"
                else:
                    orientation = "START-TO-START" if other["ENDTYPE"] == "Start" else "START-TO-END"
                if not link_exists(rid, int(other["RID"]), orientation):
                    links.append(FullTopologyLink(rid, int(other["RID"]), orientation))
    return links


def createFullTreeTableFromShapefile(
    route_features: Iterable[LineFeature | dict[str, Any]],
    route_id_field: str,
    id_link_1_name: str,
    id_link_2_name: str,
    orientation_name: str,
):
    return create_full_tree_table_from_features(
        route_features,
        route_id_field,
        id_link_1_name=id_link_1_name,
        id_link_2_name=id_link_2_name,
        orientation_name=orientation_name,
    )


def create_from_points_and_splits(
    routes: Iterable[LineFeature | dict[str, Any]],
    links: Iterable[TopologyLink | tuple[int, int] | dict[str, Any]],
    rid_field: str,
    links_up_field: str = "UpID",
    links_down_field: str = "DownID",
    feedback: FeedbackProtocol | None = None,
) -> tuple[list[PointFeature], list[PointFeature]]:
    _info(feedback, "Building upstream count from link table…")
    link_rows = ensure_links(links, down_field=links_down_field, up_field=links_up_field)
    upstream_count: dict[int, int] = defaultdict(int)
    for link in link_rows:
        upstream_count[int(link.downstream_id)] += 1

    route_features = [ensure_line_feature(feature) for feature in routes]
    all_rids = {int(feature.attributes[rid_field]) for feature in route_features}
    headwaters = {rid for rid in all_rids if upstream_count.get(rid, 0) == 0}
    single_upstream = {rid for rid in all_rids if upstream_count.get(rid, 0) == 1}

    from_points: list[PointFeature] = []
    split_points: list[PointFeature] = []
    total = len(route_features)
    for index, feature in enumerate(route_features):
        if _is_canceled(feedback):
            break
        if total:
            _set_progress(feedback, int(100 * index / max(1, total)))
        rid = int(feature.attributes[rid_field])
        upstream_vertex = feature.end_point
        if rid in headwaters:
            from_points.append(
                PointFeature({rid_field: rid}, Coordinate(upstream_vertex.x, upstream_vertex.y))
            )
        elif rid in single_upstream:
            split_points.append(
                PointFeature({}, Coordinate(upstream_vertex.x, upstream_vertex.y))
            )
    return from_points, split_points


def tree_from_flowdir(
    flowdir: FlowDirectionRasterProtocol,
    fp_features: Iterable[PointFeature | dict[str, Any]],
    split_features: Iterable[PointFeature | dict[str, Any]],
    rid_field: str,
    tolerance: float = 10000,
    feedback: FeedbackProtocol | None = None,
    from_point_id_field: str | None = None,
) -> tuple[list[LineFeature], list[TopologyLink], list[FlowPathPoint]]:
    from_points = [ensure_point_feature(feature) for feature in fp_features]
    split_points = [ensure_point_feature(feature) for feature in split_features]

    segment_id = 0
    point_id = 0
    links: list[TopologyLink] = []
    points: list[dict[str, Any]] = []
    cell_index: dict[tuple[int, int], int] = {}
    rid_to_indices: dict[int, list[int]] = {}
    initial_point: dict[int, Coordinate] = {}
    original_from_point_id: dict[int, Any] = {}

    def add_points_batch(point_rows: list[list[Any]], total_distance: float, rid: int) -> None:
        indices = rid_to_indices.setdefault(rid, [])
        for row in point_rows:
            new_row = {
                "id": int(row[0]),
                "RID": rid,
                "dist": float(total_distance - row[2]),
                "offset": float(row[3]),
                "X": float(row[4]),
                "Y": float(row[5]),
                "row": int(row[6]),
                "col": int(row[7]),
            }
            index = len(points)
            points.append(new_row)
            indices.append(index)
            cell_index.setdefault((new_row["row"], new_row["col"]), index)

    def reassign_upstream_part(old_rid: int, split_dist: float, new_rid: int) -> int:
        old_indices = rid_to_indices.get(old_rid, [])
        kept = []
        moved = []
        for index in old_indices:
            if points[index]["dist"] > split_dist:
                points[index]["RID"] = new_rid
                points[index]["dist"] = float(points[index]["dist"] - split_dist)
                moved.append(index)
            else:
                kept.append(index)
        rid_to_indices[old_rid] = kept
        rid_to_indices[new_rid] = rid_to_indices.get(new_rid, []) + moved
        return len(moved)

    def update_links_downstream(old_downstream: int, new_downstream: int) -> None:
        for index, link in enumerate(links):
            if link.downstream_id == old_downstream:
                links[index] = TopologyLink(new_downstream, link.upstream_id)

    _info(feedback, f"Tracing {len(from_points)} from-point(s)…")
    for fp_index, from_point in enumerate(from_points):
        if _is_canceled(feedback):
            break
        if from_points:
            _set_progress(feedback, int(50 * fp_index / max(1, len(from_points))))

        fp_rid = int(from_point.attributes[rid_field])
        fp_origin = from_point.attributes.get(from_point_id_field, fp_rid) if from_point_id_field else fp_rid
        current_col = flowdir.x_to_col(from_point.x)
        current_row = flowdir.y_to_row(from_point.y)

        in_raster = True
        if not flowdir.in_bounds(current_row, current_col):
            in_raster = False
        elif flowdir.get_value(current_row, current_col) not in flowdir.VALID_DIRS:
            in_raster = False
        elif (current_row, current_col) in cell_index:
            in_raster = False
            _warn(feedback, f"From point {fp_origin} already on flow path")

        if not in_raster:
            continue

        segment_id += 1
        rid = segment_id
        total_distance = 0.0
        points_list: list[list[Any]] = []
        coords_in_path: set[tuple[int, int]] = set()

        while in_raster:
            point_id += 1
            x_value = flowdir.col_to_x(current_col)
            y_value = flowdir.row_to_y(current_row)
            points_list.append([point_id, rid, total_distance, 0.0, x_value, y_value, current_row, current_col])
            coords_in_path.add((current_row, current_col))

            result = flowdir.step(current_row, current_col)
            if result is None:
                in_raster = False
                break

            next_row, next_col, current_distance = result
            if not flowdir.in_bounds(next_row, next_col):
                in_raster = False
                break
            if flowdir.get_value(next_row, next_col) not in flowdir.VALID_DIRS:
                in_raster = False
                break

            total_distance += current_distance
            if (next_row, next_col) in coords_in_path:
                in_raster = False
                _warn(
                    feedback,
                    "Infinite loop found at "
                    + f"{flowdir.col_to_x(next_col)};{flowdir.row_to_y(next_row)}",
                )
                add_points_batch(points_list, total_distance, rid)
                break

            if (next_row, next_col) in cell_index:
                confluence = points[cell_index[(next_row, next_col)]]
                confluence_rid = int(confluence["RID"])
                confluence_dist = float(confluence["dist"])
                new_upstream_rid = segment_id + 1
                moved = reassign_upstream_part(confluence_rid, confluence_dist, new_upstream_rid)
                add_points_batch(points_list, total_distance, rid)
                if moved > 0:
                    update_links_downstream(confluence_rid, new_upstream_rid)
                    links.append(TopologyLink(confluence_rid, rid))
                    links.append(TopologyLink(confluence_rid, new_upstream_rid))
                    initial_point[rid] = Coordinate(float(confluence["X"]), float(confluence["Y"]))
                    initial_point[new_upstream_rid] = Coordinate(float(confluence["X"]), float(confluence["Y"]))
                    original_from_point_id[rid] = fp_origin
                    if confluence_rid in original_from_point_id:
                        original_from_point_id[new_upstream_rid] = original_from_point_id.pop(confluence_rid)
                    segment_id = new_upstream_rid
                else:
                    _warn(feedback, f"Reach {rid} encountered another from-point")
                    links.append(TopologyLink(confluence_rid, rid))
                    original_from_point_id[rid] = fp_origin
                    initial_point[rid] = Coordinate(float(confluence["X"]), float(confluence["Y"]))
                in_raster = False
                break

            current_row = next_row
            current_col = next_col

        if points_list and rid not in original_from_point_id:
            add_points_batch(points_list, total_distance, rid)
            original_from_point_id[rid] = fp_origin

    if split_points:
        _info(feedback, f"Applying {len(split_points)} split-point(s)…")
        used_matches: set[int] = set()
        matches: list[tuple[int, float, float, float]] = []
        for split_feature in split_points:
            nearest_index = None
            nearest_distance = None
            for index, point in enumerate(points):
                distance = math.hypot(point["X"] - split_feature.x, point["Y"] - split_feature.y)
                if nearest_distance is None or distance < nearest_distance:
                    nearest_distance = distance
                    nearest_index = index
            if nearest_index is None or nearest_index in used_matches:
                continue
            if tolerance is not None and nearest_distance is not None and nearest_distance > tolerance:
                continue
            used_matches.add(nearest_index)
            point = points[nearest_index]
            matches.append((int(point["RID"]), float(point["dist"]), float(point["X"]), float(point["Y"])))
        matches.sort(key=lambda row: row[1], reverse=True)

        for old_rid, split_dist, split_x, split_y in matches:
            segment_id += 1
            new_rid = segment_id
            moved = reassign_upstream_part(old_rid, split_dist, new_rid)
            if moved <= 0:
                continue
            update_links_downstream(old_rid, new_rid)
            links.append(TopologyLink(old_rid, new_rid))
            initial_point[new_rid] = Coordinate(split_x, split_y)
            if old_rid in original_from_point_id:
                original_from_point_id[new_rid] = original_from_point_id.pop(old_rid)

    route_features: list[LineFeature] = []
    for rid in sorted(rid_to_indices.keys()):
        indices = rid_to_indices[rid]
        if not indices:
            continue
        sorted_points = sorted((points[index] for index in indices), key=lambda row: row["dist"])
        vertices = []
        if rid in initial_point:
            vertices.append(initial_point[rid])
        for row in sorted_points:
            vertices.append(Coordinate(row["X"], row["Y"]))
        if len(vertices) < 2:
            continue
        route_features.append(
            LineFeature(
                attributes={
                    rid_field: int(rid),
                    "ORIG_FID": original_from_point_id.get(rid, -999),
                },
                vertices=vertices,
            ).with_m_values()
        )

    point_rows = [
        FlowPathPoint(
            id=int(point["id"]),
            rid=int(point["RID"]),
            dist=float(point["dist"]),
            offset=float(point["offset"]),
            x=float(point["X"]),
            y=float(point["Y"]),
            row=int(point["row"]),
            col=int(point["col"]),
        )
        for point in points
    ]
    return route_features, links, point_rows


def place_points_at_regular_interval(
    routes: Iterable[LineFeature | dict[str, Any]],
    links: Iterable[TopologyLink | tuple[int, int] | dict[str, Any]],
    rid_field: str,
    interval: float,
    feedback: FeedbackProtocol | None = None,
) -> list[dict[str, Any]]:
    network = RiverNetwork()
    network.dict_attr_fields["id"] = rid_field
    network.load_data(routes, links)
    collection = PointsCollection(network, "regular_interval")
    network.place_points_at_regular_interval(interval, collection)
    _info(feedback, f"Placed {len(collection._points)} points.")
    return collection.to_table_rows({"id": "id", "reach_id": "RID", "dist": "MEAS"})


def locate_most_downstream_points(
    network_features: Iterable[LineFeature | dict[str, Any]],
    links_table: Iterable[TopologyLink | tuple[int, int] | dict[str, Any]],
    rid_field: str,
    datapoints: Iterable[dict[str, Any]],
    id_field_pts: str,
    rid_field_pts: str,
    distance_field_pts: str,
    x_field_pts: str,
    y_field_pts: str,
) -> list[PointFeature]:
    network = RiverNetwork()
    network.dict_attr_fields["id"] = rid_field
    network.load_data(network_features, links_table)

    collection = PointsCollection(network, "data")
    collection.dict_attr_fields["id"] = id_field_pts
    collection.dict_attr_fields["reach_id"] = rid_field_pts
    collection.dict_attr_fields["dist"] = distance_field_pts
    collection.dict_attr_fields["X"] = x_field_pts
    collection.dict_attr_fields["Y"] = y_field_pts
    collection.load_table(datapoints)

    result = []
    for reach in network.browse_reaches_down_to_up():
        point = reach.get_first_point(collection)
        if point is None:
            raise RuntimeError(f"No data point found for reach {reach.id}.")
        result.append(
            PointFeature(
                attributes={id_field_pts: point.id},
                point=Coordinate(point.X, point.Y),
            )
        )
    return result


def order_tree_by_flow_acc(
    network_features: Iterable[LineFeature | dict[str, Any]],
    links_table: Iterable[TopologyLink | tuple[int, int] | dict[str, Any]],
    rid_field: str,
    datapoints: Iterable[dict[str, Any]],
    id_field_pts: str,
    rid_field_pts: str,
    distance_field_pts: str,
    flow_acc_field: str,
    output_field: str = "order",
) -> list[LineFeature]:
    network = RiverNetwork()
    network.dict_attr_fields["id"] = rid_field
    network.load_data(network_features, links_table)

    collection = PointsCollection(network, "data")
    collection.dict_attr_fields["id"] = id_field_pts
    collection.dict_attr_fields["reach_id"] = rid_field_pts
    collection.dict_attr_fields["dist"] = distance_field_pts
    collection.dict_attr_fields["discharge"] = flow_acc_field
    collection.load_table(datapoints)

    network.order_reaches_by_discharge(collection, "discharge")

    output = []
    for reach in network.reaches:
        attributes = dict(reach.feature.attributes)
        attributes[output_field] = reach.order
        output.append(LineFeature(attributes=attributes, vertices=list(reach.feature.vertices)))
    return output


def relate_networks(
    network_a: Iterable[LineFeature | dict[str, Any]],
    rid_a: str,
    network_b: Iterable[LineFeature | dict[str, Any]],
    rid_b: str,
    strict_count: bool = True,
    feedback: FeedbackProtocol | None = None,
    coord_round_digits: int = 9,
) -> list[dict[str, Any]]:
    features_a = [ensure_line_feature(feature) for feature in network_a]
    features_b = [ensure_line_feature(feature) for feature in network_b]

    if strict_count and len(features_a) != len(features_b):
        raise RuntimeError(
            "The feature classes have different number of rows. "
            "This tool runs when row value is equal"
        )

    part_counts: dict[tuple[int, int], int] = {}
    total = len(features_a)
    for index, feature_a in enumerate(features_a):
        if _is_canceled(feedback):
            break
        if total:
            _set_progress(feedback, int(100 * index / max(1, total)))
        rid_a_value = int(feature_a.attributes[rid_a])
        for feature_b in features_b:
            rid_b_value = int(feature_b.attributes[rid_b])
            intersection_count = _count_line_intersections(
                feature_a,
                feature_b,
                coord_round_digits=coord_round_digits,
            )
            if intersection_count > 0:
                part_counts[(rid_a_value, rid_b_value)] = intersection_count

    by_a: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
    for (rid_a_value, rid_b_value), part_count in part_counts.items():
        by_a[rid_a_value].append((rid_a_value, rid_b_value, part_count))

    filtered_a: list[tuple[int, int, int]] = []
    for rows in by_a.values():
        max_part_count = max(row[2] for row in rows)
        filtered_a.extend(row for row in rows if row[2] == max_part_count)

    by_b: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
    for row in filtered_a:
        by_b[row[1]].append(row)

    filtered_b: list[tuple[int, int, int]] = []
    for rows in by_b.values():
        max_part_count = max(row[2] for row in rows)
        filtered_b.extend(row for row in rows if row[2] == max_part_count)

    unique_a = {row[0] for row in filtered_b}
    unique_b = {row[1] for row in filtered_b}
    if len(unique_a) != len(filtered_b) or len(unique_b) != len(filtered_b):
        _warn(feedback, "Incorrect network match")

    return [
        {
            rid_a: row[0],
            rid_b: row[1],
            "PART_COUNT": row[2],
        }
        for row in filtered_b
    ]


def _count_line_intersections(
    feature_a: LineFeature,
    feature_b: LineFeature,
    coord_round_digits: int = 9,
) -> int:
    intersections: set[tuple[float, float]] = set()
    vertices_a = feature_a.vertices
    vertices_b = feature_b.vertices
    for start_a, end_a in zip(vertices_a[:-1], vertices_a[1:]):
        for start_b, end_b in zip(vertices_b[:-1], vertices_b[1:]):
            for point in _segment_intersection_points(start_a, end_a, start_b, end_b):
                intersections.add(
                    (
                        round(float(point[0]), coord_round_digits),
                        round(float(point[1]), coord_round_digits),
                    )
                )
    return len(intersections)


def _segment_intersection_points(
    start_a: Coordinate,
    end_a: Coordinate,
    start_b: Coordinate,
    end_b: Coordinate,
    tolerance: float = 1e-9,
) -> list[tuple[float, float]]:
    ax1 = float(start_a.x)
    ay1 = float(start_a.y)
    ax2 = float(end_a.x)
    ay2 = float(end_a.y)
    bx1 = float(start_b.x)
    by1 = float(start_b.y)
    bx2 = float(end_b.x)
    by2 = float(end_b.y)

    denominator = (ax1 - ax2) * (by1 - by2) - (ay1 - ay2) * (bx1 - bx2)
    if abs(denominator) > tolerance:
        determinant_a = ax1 * ay2 - ay1 * ax2
        determinant_b = bx1 * by2 - by1 * bx2
        x_value = (determinant_a * (bx1 - bx2) - (ax1 - ax2) * determinant_b) / denominator
        y_value = (determinant_a * (by1 - by2) - (ay1 - ay2) * determinant_b) / denominator
        if _point_on_segment(x_value, y_value, ax1, ay1, ax2, ay2, tolerance) and _point_on_segment(
            x_value,
            y_value,
            bx1,
            by1,
            bx2,
            by2,
            tolerance,
        ):
            return [(x_value, y_value)]
        return []

    if not _collinear(ax1, ay1, ax2, ay2, bx1, by1, tolerance) or not _collinear(
        ax1,
        ay1,
        ax2,
        ay2,
        bx2,
        by2,
        tolerance,
    ):
        return []

    if abs(ax1 - ax2) >= abs(ay1 - ay2):
        overlap_start = max(min(ax1, ax2), min(bx1, bx2))
        overlap_end = min(max(ax1, ax2), max(bx1, bx2))
        if overlap_start > overlap_end + tolerance:
            return []
        if abs(ax2 - ax1) <= tolerance:
            overlap_values = sorted({max(min(ay1, ay2), min(by1, by2)), min(max(ay1, ay2), max(by1, by2))})
            if overlap_values[0] > overlap_values[-1] + tolerance:
                return []
            if abs(overlap_values[0] - overlap_values[-1]) <= tolerance:
                return [(ax1, overlap_values[0])]
            return [(ax1, overlap_values[0]), (ax1, overlap_values[-1])]
        start_ratio = (overlap_start - ax1) / (ax2 - ax1)
        end_ratio = (overlap_end - ax1) / (ax2 - ax1)
        start_point = (overlap_start, ay1 + start_ratio * (ay2 - ay1))
        if abs(overlap_start - overlap_end) <= tolerance:
            return [start_point]
        end_point = (overlap_end, ay1 + end_ratio * (ay2 - ay1))
        return [start_point, end_point]

    overlap_start = max(min(ay1, ay2), min(by1, by2))
    overlap_end = min(max(ay1, ay2), max(by1, by2))
    if overlap_start > overlap_end + tolerance:
        return []
    if abs(ay2 - ay1) <= tolerance:
        overlap_values = sorted({max(min(ax1, ax2), min(bx1, bx2)), min(max(ax1, ax2), max(bx1, bx2))})
        if overlap_values[0] > overlap_values[-1] + tolerance:
            return []
        if abs(overlap_values[0] - overlap_values[-1]) <= tolerance:
            return [(overlap_values[0], ay1)]
        return [(overlap_values[0], ay1), (overlap_values[-1], ay1)]
    start_ratio = (overlap_start - ay1) / (ay2 - ay1)
    end_ratio = (overlap_end - ay1) / (ay2 - ay1)
    start_point = (ax1 + start_ratio * (ax2 - ax1), overlap_start)
    if abs(overlap_start - overlap_end) <= tolerance:
        return [start_point]
    end_point = (ax1 + end_ratio * (ax2 - ax1), overlap_end)
    return [start_point, end_point]


def _point_on_segment(
    x_value: float,
    y_value: float,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    tolerance: float,
) -> bool:
    if not _collinear(x1, y1, x2, y2, x_value, y_value, tolerance):
        return False
    return (
        min(x1, x2) - tolerance <= x_value <= max(x1, x2) + tolerance
        and min(y1, y2) - tolerance <= y_value <= max(y1, y2) + tolerance
    )


def _collinear(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    x3: float,
    y3: float,
    tolerance: float,
) -> bool:
    return abs((x2 - x1) * (y3 - y1) - (y2 - y1) * (x3 - x1)) <= tolerance


def check_net_fit_from_upstream(
    routes_a: Iterable[LineFeature | dict[str, Any]],
    links_a: Iterable[TopologyLink | tuple[int, int] | dict[str, Any]],
    rid_a: str,
    routes_b: Iterable[LineFeature | dict[str, Any]],
    links_b: Iterable[TopologyLink | tuple[int, int] | dict[str, Any]],
    rid_b: str,
    frompoints_b: Iterable[PointFeature | dict[str, Any]],
    final_selection: str = "BEST_FIT",
    orig_fid_field: str = "ORIG_FID",
    frompoint_id_field: str = "id",
    feedback: FeedbackProtocol | None = None,
) -> list[dict[str, Any]]:
    ref_network = RiverNetwork()
    ref_network.dict_attr_fields["id"] = rid_a
    ref_network.dict_attr_fields["ORIG_FID"] = orig_fid_field
    ref_network.load_data(routes_a, links_a)

    second_network = RiverNetwork()
    second_network.dict_attr_fields["id"] = rid_b
    second_network.load_data(routes_b, links_b)

    frompoint_to_second_id = {}
    for from_point in frompoints_b:
        feature = ensure_point_feature(from_point)
        frompoint_to_second_id[feature.attributes[frompoint_id_field]] = feature.attributes[rid_b]

    dict_match: dict[int, list[int]] = {reach.id: [] for reach in ref_network.browse_reaches_down_to_up()}
    topological_difference = False
    for reach in ref_network.get_upstream_ends():
        list_reaches_ref = []
        current_reach = reach
        while current_reach is not None:
            list_reaches_ref.append(current_reach.id)
            current_reach = current_reach.get_downstream_reach()

        second_start_id = frompoint_to_second_id[reach.ORIG_FID]
        list_reaches_second = []
        current_reach = second_network.get_reach(second_start_id)
        while current_reach is not None:
            list_reaches_second.append(current_reach.id)
            current_reach = current_reach.get_downstream_reach()

        if len(list_reaches_ref) == len(list_reaches_second):
            for index in range(len(list_reaches_ref)):
                dict_match[list_reaches_ref[index]].append(list_reaches_second[index])
        elif final_selection == "BEST_FIT":
            topological_difference = True
            length_difference = len(list_reaches_ref) - len(list_reaches_second)
            if length_difference > 0:
                for shift in range(length_difference + 1):
                    for index in range(len(list_reaches_second)):
                        dict_match[list_reaches_ref[index + shift]].append(list_reaches_second[index])
            else:
                for shift in range(abs(length_difference) + 1):
                    for index in range(len(list_reaches_ref)):
                        dict_match[list_reaches_ref[index]].append(list_reaches_second[index + shift])
        else:
            topological_difference = True
            if len(list_reaches_ref) > len(list_reaches_second):
                for index in range(len(list_reaches_second)):
                    dict_match[list_reaches_ref[index]].append(list_reaches_second[index])
            else:
                for index in range(len(list_reaches_ref)):
                    dict_match[list_reaches_ref[index]].append(list_reaches_second[index])

    if topological_difference:
        _warn(feedback, "Topological difference between networks detected. Check results.")

    second_centroids = {
        reach.id: reach.feature.centroid()
        for reach in second_network.reaches
    }
    geometry_match = {}
    for reach in ref_network.reaches:
        centroid = reach.feature.centroid()
        geometry_match[reach.id] = min(
            second_centroids.items(),
            key=lambda item: math.hypot(item[1].x - centroid.x, item[1].y - centroid.y),
        )[0]

    result = []
    for reach in ref_network.browse_reaches_down_to_up():
        counter = Counter(dict_match[reach.id]).most_common()
        if not counter:
            continue
        matching_id, occurrences = counter[0]
        if len(counter) > 1:
            matching_id_2, occurrences_2 = counter[1]
            if occurrences == occurrences_2 and matching_id_2 == geometry_match[reach.id]:
                matching_id = matching_id_2
        percentage = occurrences / len(dict_match[reach.id])
        closest = int(matching_id == geometry_match[reach.id])
        score = percentage * 0.6 + closest * 0.4
        result.append(
            {
                rid_a: reach.id,
                "MATCH_ID": matching_id,
                "TYPO": percentage,
                "CLOSEST": closest,
                "SCORE": score,
            }
        )
    return result
