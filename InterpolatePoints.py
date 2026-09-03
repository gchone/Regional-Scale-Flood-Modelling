import math

import numpy as np

import RiverNetworkTools


def execute_InterpolatePoints(
    points_table,
    id_field_pts,
    RID_field_pts,
    Distance_field_pts,
    data_fields,
    targetpoints,
    id_field_target,
    RID_field_target,
    Distance_field_target,
    network_shp,
    links_table,
    network_RID_field,
    order_field,
    ouput_pts,
    extrapolation_value=None,
    GIStools=None,
    messages=None,
):
    if GIStools is None:
        GIStools = _autodetect_gistools()

    prepared_targets = None
    try:
        normalized_data_fields = _normalize_field_names(data_fields, deduplicate=True)

        network = RiverNetworkTools.RiverNetwork()
        network.dict_attr_fields["id"] = network_RID_field
        network.dict_attr_fields["order"] = order_field

        reach_rows = list(GIStools.DataManagement.load_line_features(network_shp, [network_RID_field, order_field]))
        link_rows = list(
            GIStools.DataManagement.load_table_rows(
                links_table,
                [
                    RiverNetworkTools.RiverNetwork.LINKS_DOWN_FIELD,
                    RiverNetworkTools.RiverNetwork.LINKS_UP_FIELD,
                ],
            )
        )
        network.load_data(reach_rows, link_rows)
        _coerce_reach_orders(network)

        point_field_names = _unique_field_names([id_field_pts, RID_field_pts, Distance_field_pts] + normalized_data_fields)
        target_field_names = _unique_field_names([id_field_target, RID_field_target, Distance_field_target])

        points_info = GIStools.DataManagement.read_table_dataset(points_table, point_field_names)
        prepared_targets = GIStools.Geoprocessing.create_points_on_route_layer(
            network_shp,
            network_RID_field,
            targetpoints,
            RID_field_target,
            Distance_field_target,
        )
        target_info = GIStools.DataManagement.read_point_dataset(prepared_targets, target_field_names)

        datacollection = RiverNetworkTools.PointsCollection(network, "data")
        datacollection.dict_attr_fields["id"] = id_field_pts
        datacollection.dict_attr_fields["reach_id"] = RID_field_pts
        datacollection.dict_attr_fields["dist"] = Distance_field_pts
        for field_name in normalized_data_fields:
            datacollection.dict_attr_fields[field_name] = field_name
        datacollection.load_table(points_info["records"])

        targetcollection = RiverNetworkTools.PointsCollection(network, "target")
        targetcollection.dict_attr_fields["id"] = id_field_target
        targetcollection.dict_attr_fields["reach_id"] = RID_field_target
        targetcollection.dict_attr_fields["dist"] = Distance_field_target
        targetcollection.load_table(target_info["records"])

        output_rows = InterpolatePoints_with_objects(
            network,
            datacollection,
            normalized_data_fields,
            targetcollection,
            extrapolation_value,
        )
        _merge_target_geometry(output_rows, target_info["records"], id_field_target, RID_field_target, Distance_field_target)

        _add_message(
            messages,
            "Interpolated {} field(s) onto {} target point(s).".format(
                len(normalized_data_fields),
                len(output_rows),
            ),
        )

        if ouput_pts is None:
            return output_rows

        return GIStools.DataManagement.write_output_points(
            ouput_pts,
            output_rows,
            target_info,
            points_info,
            normalized_data_fields,
            include_near_dist=False,
        )
    except Exception as exc:
        if messages is None:
            raise
        _add_error(messages, str(exc))
    finally:
        if prepared_targets is not None:
            try:
                GIStools.Geoprocessing.delete_layer(prepared_targets)
            except Exception:
                pass


def InterpolatePoints_with_objects(
    network,
    datacollection,
    data_fields,
    targetcollection,
    extrapolation_value,
    subdatasample=None,
):
    normalized_data_fields = _normalize_field_names(data_fields, deduplicate=True)
    if subdatasample is None:
        data_rows = datacollection.to_table_rows()
    else:
        data_rows = _coerce_subdatasample_rows(subdatasample, datacollection, normalized_data_fields)
    target_rows = targetcollection.to_table_rows()

    return _interpolate_rows_on_network(
        network,
        data_rows,
        datacollection.dict_attr_fields["reach_id"],
        datacollection.dict_attr_fields["dist"],
        normalized_data_fields,
        target_rows,
        targetcollection.dict_attr_fields["reach_id"],
        targetcollection.dict_attr_fields["dist"],
        extrapolation_value,
    )


def interpolate_points(
    data_points,
    pts_id,
    pts_rid,
    pts_dist,
    data_fields,
    target_points,
    tgt_id,
    tgt_rid,
    tgt_dist,
    reaches,
    downstream,
    upstream,
    extrapolation_value=None,
    feedback=None,
):
    del upstream

    normalized_data_fields = _normalize_field_names(data_fields, deduplicate=True)
    network = _build_network_from_dicts(reaches, downstream)

    datacollection = RiverNetworkTools.PointsCollection(network, "data")
    datacollection.dict_attr_fields["id"] = pts_id
    datacollection.dict_attr_fields["reach_id"] = pts_rid
    datacollection.dict_attr_fields["dist"] = pts_dist
    for field_name in normalized_data_fields:
        datacollection.dict_attr_fields[field_name] = field_name
    datacollection.load_table(data_points)

    targetcollection = RiverNetworkTools.PointsCollection(network, "target")
    targetcollection.dict_attr_fields["id"] = tgt_id
    targetcollection.dict_attr_fields["reach_id"] = tgt_rid
    targetcollection.dict_attr_fields["dist"] = tgt_dist
    targetcollection.load_table(target_points)

    interpolated_rows = InterpolatePoints_with_objects(
        network,
        datacollection,
        normalized_data_fields,
        targetcollection,
        extrapolation_value,
    )

    target_lookup = {}
    for row in target_points:
        target_lookup.setdefault(_point_key(row, tgt_id, tgt_rid, tgt_dist), []).append(dict(row))

    results = []
    for row in interpolated_rows:
        match_list = target_lookup.get(_point_key(row, tgt_id, tgt_rid, tgt_dist), [])
        result = match_list.pop(0) if match_list else {}
        result.update(row)
        results.append(result)

    if feedback is not None and hasattr(feedback, "pushInfo"):
        feedback.pushInfo("Interpolated values for {} target point(s)".format(len(results)))
    return results


def _interpolate_rows_on_network(
    network,
    data_rows,
    data_rid_field,
    data_dist_field,
    data_fields,
    target_rows,
    target_rid_field,
    target_dist_field,
    extrapolation_value,
):
    data_by_reach = _group_rows_by_reach(data_rows, data_rid_field)
    target_by_reach = _group_rows_by_reach(target_rows, target_rid_field)
    results = []

    if extrapolation_value is None or extrapolation_value == "CONFLUENCE":
        interp_left_right_param = None
    else:
        interp_left_right_param = float(extrapolation_value)

    for reach in network.browse_reaches_down_to_up():
        reach_targets = sorted(
            target_by_reach.get(reach.id, []),
            key=lambda row: float(row[target_dist_field]),
        )
        if len(reach_targets) == 0:
            continue

        sorteddata = sorted(
            data_by_reach.get(reach.id, []),
            key=lambda row: float(row[data_dist_field]),
        )

        down_point = None
        down_reach = reach
        downend = reach.is_downstream_end()
        same_river_down_reach_order = getattr(reach, "order", 0)
        while down_point is None and not downend:
            down_reach = down_reach.get_downstream_reach()
            same_river_down_reach_order -= 1
            if extrapolation_value != "CONFLUENCE" or down_reach.order == same_river_down_reach_order:
                downpoints = sorted(
                    data_by_reach.get(down_reach.id, []),
                    key=lambda row: float(row[data_dist_field]),
                )
                if len(downpoints) > 0:
                    down_point = dict(downpoints[-1])
                    down_point[data_dist_field] = float(down_point[data_dist_field]) - float(down_reach.length)
                    sorteddata = [down_point] + sorteddata
                downend = down_reach.is_downstream_end()
            else:
                downend = True

        up_point = None
        up_reach = reach
        upend = reach.is_upstream_end()
        while up_point is None and not upend:
            min_order = None
            for tmp_up_reach in up_reach.get_uptream_reaches():
                if min_order is None or tmp_up_reach.order < min_order:
                    min_order = tmp_up_reach.order
                    up_reach = tmp_up_reach

            uppoints = sorted(
                data_by_reach.get(up_reach.id, []),
                key=lambda row: float(row[data_dist_field]),
            )
            if len(uppoints) > 0:
                up_point = dict(uppoints[0])
                up_point[data_dist_field] = float(up_point[data_dist_field]) + float(reach.length)
                sorteddata = sorteddata + [up_point]
            upend = up_reach.is_upstream_end()

        for target_row in reach_targets:
            result = dict(target_row)
            target_distance = float(target_row[target_dist_field])
            for field_name in data_fields:
                if len(sorteddata) > 0:
                    valid_rows = [row for row in sorteddata if _as_float(row.get(field_name)) is not None]
                    if len(valid_rows) > 0:
                        data_distances = np.array([float(row[data_dist_field]) for row in valid_rows], dtype=float)
                        data_values = np.array([float(row[field_name]) for row in valid_rows], dtype=float)
                        result[field_name] = float(
                            np.interp(
                                target_distance,
                                data_distances,
                                data_values,
                                left=interp_left_right_param,
                                right=interp_left_right_param,
                            )
                        )
                    else:
                        result[field_name] = None if extrapolation_value is None else float(extrapolation_value)
                else:
                    result[field_name] = float(extrapolation_value)
            results.append(result)

    return results


def _group_rows_by_reach(rows, reach_field_name):
    grouped = {}
    for row in rows:
        rid = int(row[reach_field_name])
        grouped.setdefault(rid, []).append(dict(row))
    return grouped


def _coerce_reach_orders(network):
    for reach in network.reaches:
        order_value = _as_float(getattr(reach, "order", 0))
        reach.order = 0 if order_value is None else order_value


def _coerce_subdatasample_rows(subdatasample, datacollection, data_fields):
    rows = []
    for item in subdatasample:
        if isinstance(item, dict):
            rows.append(dict(item))
            continue

        row = {
            datacollection.dict_attr_fields["id"]: getattr(item, "id"),
            datacollection.dict_attr_fields["reach_id"]: getattr(getattr(item, "reach"), "id"),
            datacollection.dict_attr_fields["dist"]: getattr(item, "dist"),
        }
        for field_name in data_fields:
            row[field_name] = getattr(item, field_name, None)
        rows.append(row)
    return rows


def _build_network_from_dicts(reaches, downstream):
    network = RiverNetworkTools.RiverNetwork()
    network.dict_attr_fields["id"] = "RID"
    network.dict_attr_fields["order"] = "order"

    reach_rows = []
    for rid, attributes in reaches.items():
        length_value = _as_float(attributes.get("length"))
        reach_rows.append(
            RiverNetworkTools.LineFeature(
                {
                    "RID": rid,
                    "order": attributes.get("order", 0),
                    "length": 0.0 if length_value is None else length_value,
                },
                [
                    RiverNetworkTools.Coordinate(0.0, float(rid)),
                    RiverNetworkTools.Coordinate(0.0 if length_value is None else length_value, float(rid)),
                ],
            )
        )

    link_rows = []
    for up_id, down_id in downstream.items():
        link_rows.append(
            {
                RiverNetworkTools.RiverNetwork.LINKS_DOWN_FIELD: down_id,
                RiverNetworkTools.RiverNetwork.LINKS_UP_FIELD: up_id,
            }
        )

    network.load_data(reach_rows, link_rows)
    _coerce_reach_orders(network)
    return network


def _merge_target_geometry(output_rows, target_rows, id_field, rid_field, dist_field):
    target_lookup = {}
    for row in target_rows:
        target_lookup.setdefault(_point_key(row, id_field, rid_field, dist_field), []).append(row)

    for row in output_rows:
        match_rows = target_lookup.get(_point_key(row, id_field, rid_field, dist_field), [])
        if len(match_rows) == 0:
            continue
        source_row = match_rows.pop(0)
        row["X"] = source_row.get("X")
        row["Y"] = source_row.get("Y")


def _point_key(row, id_field, rid_field, dist_field):
    return (
        int(row[id_field]),
        int(row[rid_field]),
        float(row[dist_field]),
    )


def _autodetect_gistools():
    try:
        import ArcGIStools

        return ArcGIStools
    except Exception:
        pass

    try:
        import QGIStools

        return QGIStools
    except Exception:
        pass

    raise ValueError("A GIStools package must be provided.")


def _normalize_field_names(field_names, deduplicate=False):
    if field_names in [None, ""]:
        return []
    if isinstance(field_names, str):
        names = [item.strip() for item in field_names.split(";")]
    else:
        names = [str(item).strip() for item in field_names]
    names = [name for name in names if name not in [None, ""]]
    if not deduplicate:
        return names
    return _unique_field_names(names)


def _unique_field_names(field_names):
    unique_names = []
    seen_names = set()
    for field_name in field_names:
        if field_name in seen_names:
            continue
        seen_names.add(field_name)
        unique_names.append(field_name)
    return unique_names


def _as_float(value):
    if value in [None, ""]:
        return None
    if hasattr(value, "isNull"):
        try:
            if value.isNull():
                return None
        except Exception:
            pass
    try:
        float_value = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(float_value):
        return None
    return float_value


def _add_message(messages, message):
    if messages is not None:
        messages.add_message(message)


def _add_error(messages, message):
    if messages is not None:
        messages.add_error(message)
    raise RuntimeError(message)
