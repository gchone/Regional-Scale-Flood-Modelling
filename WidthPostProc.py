from __future__ import annotations

import math
import os
import uuid

import RiverNetworkTools
from InterpolatePoints import InterpolatePoints_with_objects
from LocatePointsAlongRoutes import execute_LocatePointsAlongRoutes


def execute_WidthPostProc(
    network_shp,
    RID_field,
    main_channel_field,
    network_main_only,
    RID_field_main,
    network_main_l_field,
    order_field,
    routes_links,
    network_main_only_links,
    widthdata,
    widthid,
    width_RID_field,
    width_distance,
    width_field,
    datapoints,
    id_field_datapts,
    distance_field_datapts,
    rid_field_datapts,
    output_table,
    GIStools=None,
    messages=None,
):
    if GIStools is None:
        GIStools = _autodetect_gistools()

    network_dataset = _open_vector_dataset(GIStools, network_shp)
    network_main_dataset = _open_vector_dataset(GIStools, network_main_only)
    routes_links_dataset = _open_vector_dataset(GIStools, routes_links)
    network_main_only_links_dataset = _open_vector_dataset(GIStools, network_main_only_links)
    widthdata_dataset = _open_vector_dataset(GIStools, widthdata)
    datapoints_dataset = _open_vector_dataset(GIStools, datapoints)

    temporary_datasets = []
    try:
        split_features = list(
            GIStools.DataManagement.load_line_features(
                network_dataset,
                _unique_field_names([RID_field, main_channel_field]),
            )
        )
        if len(split_features) == 0:
            _add_error(messages, "The full split network does not contain any valid reach features.")

        main_network_features = list(
            GIStools.DataManagement.load_line_features(
                network_main_dataset,
                _unique_field_names([RID_field_main, network_main_l_field, order_field]),
            )
        )
        if len(main_network_features) == 0:
            _add_error(messages, "The main-channel-only network does not contain any valid reach features.")

        main_network_info = GIStools.DataManagement.read_table_dataset(
            network_main_dataset,
            _unique_field_names([RID_field_main, network_main_l_field, order_field]),
        )
        widthdata_info = GIStools.DataManagement.read_point_dataset(
            widthdata_dataset,
            _unique_field_names([widthid, width_RID_field, width_distance, width_field]),
        )
        if len(widthdata_info["records"]) == 0:
            _add_error(messages, "The widthdata layer does not contain any point records.")

        datapoints_info = GIStools.DataManagement.read_table_dataset(
            datapoints_dataset,
            _unique_field_names([id_field_datapts, rid_field_datapts, distance_field_datapts]),
        )
        if len(datapoints_info["records"]) == 0:
            _add_error(messages, "The datapoints layer does not contain any target records.")

        main_link_rows = list(
            GIStools.DataManagement.load_table_rows(
                network_main_only_links_dataset,
                [
                    RiverNetworkTools.RiverNetwork.LINKS_DOWN_FIELD,
                    RiverNetworkTools.RiverNetwork.LINKS_UP_FIELD,
                ],
            )
        )
        split_link_rows = list(
            GIStools.DataManagement.load_table_rows(
                routes_links_dataset,
                [
                    RiverNetworkTools.RiverNetwork.LINKS_DOWN_FIELD,
                    RiverNetworkTools.RiverNetwork.LINKS_UP_FIELD,
                ],
            )
        )

        split_spatial_reference = GIStools.DataManagement.get_spatial_reference(network_dataset)
        main_spatial_reference = GIStools.DataManagement.get_spatial_reference(network_main_dataset)
        width_spatial_reference = widthdata_info.get("spatial_reference", split_spatial_reference)

        split_to_main_field = _make_unique_field_name(
            "MAIN_RID",
            [RID_field, main_channel_field, RID_field_main, width_RID_field, rid_field_datapts],
        )
        split_to_main_rid = _find_parent_containing_reaches(
            split_features,
            RID_field,
            network_main_dataset,
            RID_field_main,
            output_table,
            GIStools,
            split_to_main_field,
            split_spatial_reference,
            temporary_datasets,
        )

        main_reach_ids = [
            int(feature.attributes[RID_field])
            for feature in split_features
            if _is_true(feature.attributes.get(main_channel_field))
        ]
        secondary_reach_ids = [
            int(feature.attributes[RID_field])
            for feature in split_features
            if not _is_true(feature.attributes.get(main_channel_field))
        ]

        _add_message(messages, "Processing main channels")
        main_width_rows = _build_main_width_rows(
            split_features,
            main_reach_ids,
            split_to_main_rid,
            RID_field,
            network_main_dataset,
            main_network_features,
            widthdata_info["records"],
            widthid,
            width_RID_field,
            width_distance,
            width_field,
            RID_field_main,
            network_main_l_field,
            output_table,
            GIStools,
            messages,
            main_spatial_reference,
            temporary_datasets,
        )

        main_width_pts = _build_temp_table_path(output_table, "widthpostproc_main_width_pts", GIStools)
        temporary_datasets.append(main_width_pts)
        GIStools.DataManagement.write_output_table(
            main_width_pts,
            main_width_rows,
            _empty_input_info(),
            [
                _table_field_spec(widthdata_info, widthid, default_dtype="int"),
                _table_field_spec(widthdata_info, width_field, default_dtype="float"),
                _table_field_spec(widthdata_info, width_distance, default_dtype="float"),
                _table_field_spec(main_network_info, RID_field_main, default_dtype="int"),
            ],
        )
        main_width_info = GIStools.DataManagement.read_table_dataset(
            _open_vector_dataset(GIStools, main_width_pts),
            [widthid, width_field, width_distance, RID_field_main],
        )

        network = RiverNetworkTools.RiverNetwork()
        network.dict_attr_fields["id"] = RID_field_main
        network.dict_attr_fields["order"] = order_field
        network.load_data(main_network_features, main_link_rows)
        _coerce_reach_orders(network)

        width_pts_collection = RiverNetworkTools.PointsCollection(network, "main_width")
        width_pts_collection.dict_attr_fields["id"] = widthid
        width_pts_collection.dict_attr_fields["reach_id"] = RID_field_main
        width_pts_collection.dict_attr_fields["dist"] = width_distance
        width_pts_collection.dict_attr_fields[width_field] = width_field
        width_pts_collection.load_table(main_width_info["records"])

        targetcollection = RiverNetworkTools.PointsCollection(network, "target")
        targetcollection.dict_attr_fields["id"] = id_field_datapts
        targetcollection.dict_attr_fields["reach_id"] = rid_field_datapts
        targetcollection.dict_attr_fields["dist"] = distance_field_datapts
        targetcollection.load_table(datapoints_info["records"])

        interp_main_width_rows = InterpolatePoints_with_objects(
            network,
            width_pts_collection,
            [width_field],
            targetcollection,
            "CONFLUENCE",
        )
        interp_main_width_rows = _sorted_target_rows(
            interp_main_width_rows,
            id_field_datapts,
            rid_field_datapts,
            distance_field_datapts,
        )

        if len(secondary_reach_ids) != 0:
            _add_message(messages, "Projecting secondary channel points on main channels")
            augmented_split_features = _augment_split_features(
                split_features,
                split_to_main_field,
                split_to_main_rid,
                RID_field,
            )
            network_allchannels = RiverNetworkTools.RiverNetwork()
            network_allchannels.dict_attr_fields["id"] = RID_field
            network_allchannels.dict_attr_fields["main"] = main_channel_field
            network_allchannels.dict_attr_fields["main_RID"] = split_to_main_field
            network_allchannels.load_data(augmented_split_features, split_link_rows, load_secondary_channel=True)

            secondary_channel_rid_field = _make_unique_field_name(
                width_RID_field + "_split",
                [widthid, width_field, width_RID_field, width_distance, RID_field_main, "MEAS"],
            )
            secondary_width_rows = _project_secondary_width_rows(
                network_allchannels,
                secondary_reach_ids,
                widthdata_info["records"],
                widthid,
                width_field,
                width_RID_field,
                secondary_channel_rid_field,
                main_network_features,
                RID_field_main,
                output_table,
                GIStools,
                main_spatial_reference,
                width_spatial_reference,
            )

            if len(secondary_width_rows) != 0:
                secondary_width_pts = _build_temp_table_path(output_table, "widthpostproc_secondary_width_pts", GIStools)
                temporary_datasets.append(secondary_width_pts)
                GIStools.DataManagement.write_output_table(
                    secondary_width_pts,
                    secondary_width_rows,
                    _empty_input_info(),
                    [
                        _table_field_spec(widthdata_info, widthid, default_dtype="int"),
                        _table_field_spec(main_network_info, RID_field_main, default_dtype="int"),
                        _simple_table_field_spec("MEAS", "float"),
                        _table_field_spec(widthdata_info, width_field, default_dtype="float"),
                        _renamed_table_field_spec(
                            widthdata_info,
                            width_RID_field,
                            secondary_channel_rid_field,
                            default_dtype="int",
                        ),
                    ],
                )
                secondary_width_info = GIStools.DataManagement.read_table_dataset(
                    _open_vector_dataset(GIStools, secondary_width_pts),
                    [widthid, width_field, "MEAS", RID_field_main, secondary_channel_rid_field],
                )

                _process_secondary_channel_contributions(
                    network,
                    split_features,
                    widthdata_info["records"],
                    main_width_info["records"],
                    secondary_width_info["records"],
                    targetcollection,
                    interp_main_width_rows,
                    widthid,
                    width_RID_field,
                    width_distance,
                    width_field,
                    RID_field,
                    RID_field_main,
                    secondary_channel_rid_field,
                    id_field_datapts,
                    rid_field_datapts,
                    distance_field_datapts,
                    messages,
                )

        result_table = _build_temp_table_path(output_table, "widthpostproc_result", GIStools)
        temporary_datasets.append(result_table)
        GIStools.DataManagement.write_output_table(
            result_table,
            interp_main_width_rows,
            _empty_input_info(),
            [
                _table_field_spec(datapoints_info, id_field_datapts, default_dtype="int"),
                _table_field_spec(datapoints_info, rid_field_datapts, default_dtype="int"),
                _table_field_spec(datapoints_info, distance_field_datapts, default_dtype="float"),
                _table_field_spec(widthdata_info, width_field, default_dtype="float"),
            ],
        )

        _materialize_route_measure_points(
            _open_vector_dataset(GIStools, result_table),
            rid_field_datapts,
            distance_field_datapts,
            network_main_dataset,
            RID_field_main,
            output_table,
            GIStools,
            messages,
        )
        return output_table
    except Exception as exc:
        if messages is None:
            raise
        _add_error(messages, str(exc))
    finally:
        for dataset_path in reversed(temporary_datasets):
            try:
                GIStools.Geoprocessing.delete_dataset(dataset_path)
            except Exception:
                pass


def _find_parent_containing_reaches(
    split_features,
    split_rid_field,
    unsplit_network,
    unsplit_rid_field,
    output_reference,
    GIStools,
    split_output_field,
    spatial_reference,
    temporary_datasets,
):
    midpoint_rows = []
    for feature in split_features:
        split_rid = int(feature.attributes[split_rid_field])
        midpoint = feature.interpolate(float(feature.length()) / 2.0)
        midpoint_rows.append(
            {
                "X": float(midpoint.x),
                "Y": float(midpoint.y),
                split_output_field: split_rid,
            }
        )

    midpoint_dataset = _build_temp_vector_path(output_reference, "widthpostproc_midpoints", GIStools)
    temporary_datasets.append(midpoint_dataset)
    GIStools.DataManagement.write_bed_assessment_points(
        midpoint_dataset,
        midpoint_rows,
        _empty_input_info(),
        [{"name": split_output_field, "dtype": "int"}],
        spatial_reference=spatial_reference,
    )

    snapped_info = GIStools.Geoprocessing.snap_points_to_nearest_line(
        _open_vector_dataset(GIStools, midpoint_dataset),
        unsplit_network,
        field_names=[unsplit_rid_field],
        tolerance=None,
    )

    mapping = {}
    for row in snapped_info["records"]:
        split_rid = row.get(split_output_field)
        unsplit_rid = row.get(unsplit_rid_field)
        if split_rid in [None, ""] or unsplit_rid in [None, ""]:
            continue
        mapping[int(split_rid)] = int(unsplit_rid)
    return mapping


def _build_main_width_rows(
    split_features,
    main_reach_ids,
    split_to_main_rid,
    split_rid_field,
    main_network_dataset,
    main_network_features,
    width_rows,
    widthid,
    width_rid_field,
    width_distance_field,
    width_field,
    rid_field_main,
    main_length_field,
    output_reference,
    GIStools,
    messages,
    spatial_reference,
    temporary_datasets,
):
    main_reach_id_set = {int(rid) for rid in main_reach_ids}
    if len(main_reach_id_set) == 0:
        raise ValueError("No reaches were flagged as main channels in the full split network.")

    start_split_field = _make_unique_field_name(
        "RID_A",
        [widthid, width_rid_field, width_distance_field, width_field, rid_field_main],
    )
    start_rows = []
    for feature in split_features:
        split_rid = int(feature.attributes[split_rid_field])
        if split_rid not in main_reach_id_set:
            continue
        main_rid = split_to_main_rid.get(split_rid)
        if main_rid is None:
            raise ValueError("Main-channel split reach {} could not be matched to the main-only network.".format(split_rid))
        start_rows.append(
            {
                "X": float(feature.start_point.x),
                "Y": float(feature.start_point.y),
                start_split_field: split_rid,
                rid_field_main: int(main_rid),
            }
        )

    if len(start_rows) == 0:
        raise ValueError("No main-channel split reaches were available for width correction.")

    start_pts = _build_temp_vector_path(output_reference, "widthpostproc_starts", GIStools)
    temporary_datasets.append(start_pts)
    GIStools.DataManagement.write_bed_assessment_points(
        start_pts,
        start_rows,
        _empty_input_info(),
        [
            {"name": start_split_field, "dtype": "int"},
            {"name": rid_field_main, "dtype": "int"},
        ],
        spatial_reference=spatial_reference,
    )

    splits_along = _build_temp_table_path(output_reference, "widthpostproc_splits_along", GIStools)
    temporary_datasets.append(splits_along)
    execute_LocatePointsAlongRoutes(
        _open_vector_dataset(GIStools, start_pts),
        rid_field_main,
        main_network_dataset,
        rid_field_main,
        splits_along,
        1,
        GIStools=GIStools,
        messages=messages,
    )

    start_measures = GIStools.DataManagement.read_table_dataset(
        _open_vector_dataset(GIStools, splits_along),
        [start_split_field, rid_field_main, "MEAS"],
    )
    start_measure_by_split = {
        int(row[start_split_field]): float(row["MEAS"])
        for row in start_measures["records"]
        if row.get(start_split_field) not in [None, ""] and _as_float(row.get("MEAS")) is not None
    }

    main_length_by_rid = {}
    for feature in main_network_features:
        rid_value = int(feature.attributes[rid_field_main])
        length_value = _as_float(feature.attributes.get(main_length_field))
        if length_value is None:
            length_value = float(feature.length())
        main_length_by_rid[rid_value] = float(length_value)

    output_rows = []
    for row in width_rows:
        split_rid = row.get(width_rid_field)
        if split_rid in [None, ""]:
            continue
        split_rid = int(split_rid)
        if split_rid not in main_reach_id_set:
            continue

        main_rid = split_to_main_rid.get(split_rid)
        start_measure = _as_float(start_measure_by_split.get(split_rid))
        point_distance = _as_float(row.get(width_distance_field))
        max_length = _as_float(main_length_by_rid.get(main_rid))
        if main_rid is None or start_measure is None or point_distance is None or max_length is None:
            raise ValueError("Could not correct width distances for main-channel split reach {}.".format(split_rid))

        output_rows.append(
            {
                widthid: row.get(widthid),
                width_field: row.get(width_field),
                width_distance_field: min(point_distance + start_measure, max_length),
                rid_field_main: int(main_rid),
            }
        )

    if len(output_rows) == 0:
        raise ValueError("No widthdata points were found on main-channel reaches.")
    return output_rows


def _augment_split_features(split_features, main_rid_field_name, split_to_main_rid, split_rid_field):
    augmented = []
    for feature in split_features:
        attributes = dict(feature.attributes)
        split_rid = int(attributes[split_rid_field])
        attributes[main_rid_field_name] = split_to_main_rid.get(split_rid)
        augmented.append(RiverNetworkTools.LineFeature(attributes, list(feature.vertices)))
    return augmented


def _project_secondary_width_rows(
    network_allchannels,
    secondary_reach_ids,
    width_rows,
    widthid,
    width_field,
    width_rid_field,
    secondary_channel_rid_field,
    main_network_features,
    rid_field_main,
    output_reference,
    GIStools,
    main_spatial_reference,
    point_spatial_reference,
):
    main_features_by_rid = {
        int(feature.attributes[rid_field_main]): feature
        for feature in main_network_features
    }
    secondary_rows_by_rid = {}
    for row in width_rows:
        rid_value = row.get(width_rid_field)
        if rid_value in [None, ""]:
            continue
        rid_value = int(rid_value)
        secondary_rows_by_rid.setdefault(rid_value, []).append(
            {
                "X": row.get("X"),
                "Y": row.get("Y"),
                widthid: row.get(widthid),
                width_field: row.get(width_field),
                secondary_channel_rid_field: rid_value,
            }
        )

    projected_rows = []
    for secondary_rid in secondary_reach_ids:
        if secondary_rid not in secondary_rows_by_rid:
            continue

        currentreach = network_allchannels.get_reach(secondary_rid)
        downstream_mainreach = None
        temp_reach = currentreach
        while not temp_reach.is_downstream_end():
            temp_reach = temp_reach.get_downstream_reach()
            if _is_true(getattr(temp_reach, "main", 0)):
                downstream_mainreach = temp_reach
                break
        if downstream_mainreach is None:
            raise IndexError(
                "Secondary channel {} does not reach any main channel downstream.".format(currentreach.id)
            )

        main_rid = getattr(downstream_mainreach, "main_RID", None)
        route_feature = None if main_rid is None else main_features_by_rid.get(int(main_rid))
        if route_feature is None:
            raise ValueError(
                "Could not find main-network reach {} for secondary channel {}.".format(main_rid, secondary_rid)
            )

        local_temporary = []
        try:
            route_dataset = _build_temp_vector_path(output_reference, "widthpostproc_secondary_route", GIStools)
            local_temporary.append(route_dataset)
            GIStools.DataManagement.write_line_features(
                route_dataset,
                [route_feature],
                _empty_input_info(),
                [{"name": rid_field_main, "dtype": "int"}],
                spatial_reference=main_spatial_reference,
            )

            point_dataset = _build_temp_vector_path(output_reference, "widthpostproc_secondary_points", GIStools)
            local_temporary.append(point_dataset)
            GIStools.DataManagement.write_bed_assessment_points(
                point_dataset,
                secondary_rows_by_rid[secondary_rid],
                _empty_input_info(),
                [
                    {"name": widthid, "dtype": "int"},
                    {"name": width_field, "dtype": "float"},
                    {"name": secondary_channel_rid_field, "dtype": "int"},
                ],
                spatial_reference=point_spatial_reference,
            )

            located_info = GIStools.Geoprocessing.locate_features_along_routes_records(
                _open_vector_dataset(GIStools, point_dataset),
                _open_vector_dataset(GIStools, route_dataset),
                rid_field_main,
                10000,
                field_names=[widthid, width_field, secondary_channel_rid_field],
            )
            projected_rows.extend(
                [
                    {
                        widthid: row.get(widthid),
                        rid_field_main: row.get(rid_field_main),
                        "MEAS": row.get("MEAS"),
                        width_field: row.get(width_field),
                        secondary_channel_rid_field: row.get(secondary_channel_rid_field),
                    }
                    for row in located_info["records"]
                ]
            )
        finally:
            for dataset_path in reversed(local_temporary):
                try:
                    GIStools.Geoprocessing.delete_dataset(dataset_path)
                except Exception:
                    pass
    return projected_rows


def _process_secondary_channel_contributions(
    network,
    split_features,
    width_rows,
    main_width_rows,
    secondary_width_rows,
    targetcollection,
    running_rows,
    widthid,
    width_rid_field,
    width_distance_field,
    width_field,
    split_rid_field,
    rid_field_main,
    secondary_channel_rid_field,
    target_id_field,
    target_rid_field,
    target_dist_field,
    messages,
):
    datacollection = RiverNetworkTools.PointsCollection(network, "secondary_width")
    datacollection.dict_attr_fields["id"] = widthid
    datacollection.dict_attr_fields["reach_id"] = rid_field_main
    datacollection.dict_attr_fields["dist"] = "MEAS"
    datacollection.dict_attr_fields[width_field] = width_field
    datacollection.dict_attr_fields[secondary_channel_rid_field] = secondary_channel_rid_field
    datacollection.load_table(secondary_width_rows)

    fullnetwork = RiverNetworkTools.FullRiverNetwork()
    fullnetwork.dict_attr_fields["id"] = split_rid_field
    fullnetwork.load_data(split_features)

    width_pts_collection2 = RiverNetworkTools.PointsCollection(fullnetwork, "full_width")
    width_pts_collection2.dict_attr_fields["id"] = widthid
    width_pts_collection2.dict_attr_fields["reach_id"] = width_rid_field
    width_pts_collection2.dict_attr_fields["dist"] = width_distance_field
    width_pts_collection2.dict_attr_fields[width_field] = width_field
    width_pts_collection2.load_table(width_rows)

    running_rows[:] = _sorted_target_rows(running_rows, target_id_field, target_rid_field, target_dist_field)
    running_keys = _target_key_sequence(running_rows, target_id_field, target_rid_field, target_dist_field)

    secondary_rows_by_rid = _group_rows_by_int_field(secondary_width_rows, secondary_channel_rid_field)
    secondary_rows_by_id = {
        int(row[widthid]): dict(row)
        for row in secondary_width_rows
        if row.get(widthid) not in [None, ""]
    }
    main_width_rows_by_id = {
        int(row[widthid]): dict(row)
        for row in main_width_rows
        if row.get(widthid) not in [None, ""]
    }

    secondary_rids = sorted(secondary_rows_by_rid.keys())
    for index, secondary_rid in enumerate(secondary_rids, start=1):
        _add_message(
            messages,
            "Processing secondary channels ({}/{})".format(index, len(secondary_rids)),
        )
        subdatasample = sorted(
            [dict(row) for row in secondary_rows_by_rid[secondary_rid]],
            key=lambda row: float(row["MEAS"]),
        )

        current_reach = fullnetwork.get_reach(secondary_rid)
        first_point = current_reach.get_first_point(width_pts_collection2)
        last_point = current_reach.get_last_point(width_pts_collection2)
        if first_point is None or last_point is None:
            raise ValueError("Secondary channel {} does not contain any source width points.".format(secondary_rid))
        projecteddownpt = dict(secondary_rows_by_id[first_point.id])
        projecteduppt = dict(secondary_rows_by_id[last_point.id])

        downstream_reach = network.get_reach(projecteduppt[rid_field_main])
        while (not downstream_reach.is_downstream_end()) and downstream_reach.id != int(projecteddownpt[rid_field_main]):
            downstream_reach = downstream_reach.get_downstream_reach()
        inverted = (
            downstream_reach.id != int(projecteddownpt[rid_field_main])
            or float(projecteddownpt["MEAS"]) > float(projecteduppt["MEAS"])
        )
        if inverted:
            projecteddownpt, projecteduppt = projecteduppt, projecteddownpt

        if not inverted:
            extremity_pts = current_reach.get_upstreamnextpts(width_pts_collection2)
        else:
            extremity_pts = current_reach.get_downstreamnextpts(width_pts_collection2)
        furthest_upstream = _find_furthest_upstream_boundary_row(
            extremity_pts,
            secondary_rows_by_id,
            main_width_rows_by_id,
            network,
            projecteduppt,
            rid_field_main,
            width_distance_field,
            width_field,
        )
        if furthest_upstream is not None:
            subdatasample.append(
                _add_zero_width_boundary_row(
                    datacollection,
                    furthest_upstream,
                    secondary_channel_rid_field,
                    secondary_rid,
                    widthid,
                    rid_field_main,
                    width_field,
                    furthest_upstream["dist_field"],
                )
            )

        if not inverted:
            extremity_pts = current_reach.get_downstreamnextpts(width_pts_collection2)
        else:
            extremity_pts = current_reach.get_upstreamnextpts(width_pts_collection2)
        furthest_downstream = _find_furthest_downstream_boundary_row(
            extremity_pts,
            secondary_rows_by_id,
            main_width_rows_by_id,
            network,
            projecteddownpt,
            rid_field_main,
            width_distance_field,
            width_field,
        )
        if furthest_downstream is not None:
            subdatasample.append(
                _add_zero_width_boundary_row(
                    datacollection,
                    furthest_downstream,
                    secondary_channel_rid_field,
                    secondary_rid,
                    widthid,
                    rid_field_main,
                    width_field,
                    furthest_downstream["dist_field"],
                )
            )

        subdatasample = sorted(subdatasample, key=lambda row: float(row["MEAS"]))
        tmp_rows = InterpolatePoints_with_objects(
            network,
            datacollection,
            [width_field],
            targetcollection,
            0,
            subdatasample=subdatasample,
        )
        tmp_rows = _sorted_target_rows(tmp_rows, target_id_field, target_rid_field, target_dist_field)
        if _target_key_sequence(tmp_rows, target_id_field, target_rid_field, target_dist_field) != running_keys:
            raise ValueError("Secondary-channel interpolation output could not be aligned with the target datapoints.")

        for base_row, extra_row in zip(running_rows, tmp_rows):
            base_value = _as_float(base_row.get(width_field))
            extra_value = _as_float(extra_row.get(width_field))
            base_row[width_field] = (0.0 if base_value is None else base_value) + (0.0 if extra_value is None else extra_value)


def _find_furthest_upstream_boundary_row(
    extremity_pts,
    secondary_rows_by_id,
    main_width_rows_by_id,
    network,
    projecteduppt,
    rid_field_main,
    width_distance_field,
    width_field,
):
    del width_field
    maxdist = 0.0
    furthest = None
    for pt in _candidate_rows(extremity_pts, secondary_rows_by_id, main_width_rows_by_id, width_distance_field):
        reach = network.get_reach(pt[rid_field_main])
        reachdist = 0.0
        while reach.id != int(projecteduppt[rid_field_main]):
            if reach.is_downstream_end():
                raise IndexError
            reach = reach.get_downstream_reach()
            reachdist += float(reach.length)
        distance = float(pt["distance"]) - float(projecteduppt["MEAS"]) + reachdist
        if distance > maxdist:
            maxdist = distance
            furthest = dict(pt)
    return furthest


def _find_furthest_downstream_boundary_row(
    extremity_pts,
    secondary_rows_by_id,
    main_width_rows_by_id,
    network,
    projecteddownpt,
    rid_field_main,
    width_distance_field,
    width_field,
):
    del width_field
    maxdist = 0.0
    furthest = None
    for pt in _candidate_rows(extremity_pts, secondary_rows_by_id, main_width_rows_by_id, width_distance_field):
        reach = network.get_reach(projecteddownpt[rid_field_main])
        reachdist = 0.0
        skip_pt = False
        while reach.id != int(pt[rid_field_main]):
            if reach.is_downstream_end():
                skip_pt = True
                break
            reach = reach.get_downstream_reach()
            reachdist += float(reach.length)
        if skip_pt:
            continue
        distance = float(projecteddownpt["MEAS"]) - float(pt["distance"]) + reachdist
        if distance > maxdist:
            maxdist = distance
            furthest = dict(pt)
    return furthest


def _candidate_rows(extremity_pts, secondary_rows_by_id, main_width_rows_by_id, width_distance_field):
    extremity_ids = [int(point.id) for point in extremity_pts]
    for point_id in extremity_ids:
        row = secondary_rows_by_id.get(point_id)
        if row is not None:
            yield {
                "row": row,
                "distance": row["MEAS"],
                "dist_field": "MEAS",
                **row,
            }
    for point_id in extremity_ids:
        row = main_width_rows_by_id.get(point_id)
        if row is not None:
            yield {
                "row": row,
                "distance": row[width_distance_field],
                "dist_field": width_distance_field,
                **row,
            }


def _add_zero_width_boundary_row(
    datacollection,
    furthest_row,
    secondary_channel_rid_field,
    secondary_rid,
    widthid,
    rid_field_main,
    width_field,
    distance_field_name,
):
    newpt = datacollection.river_network.get_reach(int(furthest_row[rid_field_main])).add_point(
        float(furthest_row[distance_field_name]),
        datacollection,
    )
    setattr(newpt, width_field, 0.0)
    setattr(newpt, secondary_channel_rid_field, int(secondary_rid))
    return {
        widthid: int(newpt.id),
        rid_field_main: int(newpt.reach.id),
        "MEAS": float(newpt.dist),
        width_field: 0.0,
        secondary_channel_rid_field: int(secondary_rid),
    }


def _materialize_route_measure_points(
    input_points,
    input_rid_field,
    input_dist_field,
    routes,
    route_rid_field,
    output_path,
    GIStools,
    messages,
):
    input_info = GIStools.DataManagement.read_table_dataset(input_points)
    route_geometries = _read_route_vertex_lookup(GIStools, routes, route_rid_field)
    spatial_reference = GIStools.DataManagement.get_spatial_reference(routes)

    rows = []
    skipped_missing_route = 0
    skipped_missing_measure = 0
    for row in input_info["records"]:
        rid_value = row.get(input_rid_field)
        measure_value = _as_float(row.get(input_dist_field))
        if rid_value in [None, ""] or route_geometries.get(rid_value) in [None, []]:
            skipped_missing_route += 1
            continue
        if measure_value is None:
            skipped_missing_measure += 1
            continue

        x_value, y_value = _point_from_measure(route_geometries[rid_value], measure_value)
        output_row = dict(row)
        output_row["X"] = float(x_value)
        output_row["Y"] = float(y_value)
        rows.append(output_row)

    if len(rows) == 0:
        _add_error(messages, "No route-event points could be created from the supplied RID/measure records.")

    if skipped_missing_route != 0:
        _add_warning(
            messages,
            "{} record(s) were skipped because their RID was missing from the route network.".format(
                skipped_missing_route
            ),
        )
    if skipped_missing_measure != 0:
        _add_warning(
            messages,
            "{} record(s) were skipped because their measure value was empty or invalid.".format(
                skipped_missing_measure
            ),
        )

    GIStools.DataManagement.write_bed_assessment_points(
        output_path,
        rows,
        input_info,
        [],
        spatial_reference=spatial_reference,
    )
    _add_message(messages, "Created {} route-event point(s).".format(len(rows)))
    return output_path


def _read_route_vertex_lookup(GIStools, routes, route_rid_field):
    route_lookup = {}
    for feature in GIStools.DataManagement.load_line_features(routes, [route_rid_field]):
        rid_value = feature.attributes.get(route_rid_field)
        if rid_value in [None, ""]:
            continue
        if rid_value not in route_lookup:
            route_lookup[rid_value] = []
        route_lookup[rid_value].append(list(feature.vertices))
    return route_lookup


def _point_from_measure(route_parts, measure):
    segments, total_measure = _build_route_segments(route_parts)
    if len(segments) == 0:
        raise ValueError("A route geometry did not contain any valid vertices.")
    target_measure = max(0.0, min(float(measure), total_measure))
    for segment in segments:
        if segment["end_measure"] >= target_measure:
            segment_span = segment["end_measure"] - segment["start_measure"]
            if segment_span == 0.0:
                return segment["start_x"], segment["start_y"]
            ratio = (target_measure - segment["start_measure"]) / segment_span
            return (
                segment["start_x"] + ratio * (segment["end_x"] - segment["start_x"]),
                segment["start_y"] + ratio * (segment["end_y"] - segment["start_y"]),
            )
    last_segment = segments[-1]
    return last_segment["end_x"], last_segment["end_y"]


def _build_route_segments(route_parts):
    segments = []
    total_measure = 0.0
    for part in route_parts:
        for start_vertex, end_vertex in zip(part[:-1], part[1:]):
            start_x = _vertex_x(start_vertex)
            start_y = _vertex_y(start_vertex)
            end_x = _vertex_x(end_vertex)
            end_y = _vertex_y(end_vertex)
            geometric_length = math.hypot(end_x - start_x, end_y - start_y)
            start_measure = _vertex_measure(start_vertex)
            end_measure = _vertex_measure(end_vertex)
            if start_measure is not None and end_measure is not None and end_measure >= start_measure:
                segment_start_measure = float(start_measure)
                segment_end_measure = float(end_measure)
            else:
                segment_start_measure = total_measure
                segment_end_measure = total_measure + geometric_length
            segments.append(
                {
                    "start_x": start_x,
                    "start_y": start_y,
                    "end_x": end_x,
                    "end_y": end_y,
                    "start_measure": segment_start_measure,
                    "end_measure": segment_end_measure,
                }
            )
            total_measure = max(total_measure + geometric_length, segment_end_measure)
    return segments, total_measure


def _vertex_x(vertex):
    if hasattr(vertex, "x"):
        return float(vertex.x)
    return float(vertex[0])


def _vertex_y(vertex):
    if hasattr(vertex, "y"):
        return float(vertex.y)
    return float(vertex[1])


def _vertex_measure(vertex):
    measure = getattr(vertex, "m", None)
    if measure in [None, ""]:
        return None
    try:
        return float(measure)
    except (TypeError, ValueError):
        return None


def _sorted_target_rows(rows, id_field, rid_field, dist_field):
    return sorted(
        rows,
        key=lambda row: (
            int(row[id_field]),
            int(row[rid_field]),
            float(row[dist_field]),
        ),
    )


def _target_key_sequence(rows, id_field, rid_field, dist_field):
    return [
        (int(row[id_field]), int(row[rid_field]), float(row[dist_field]))
        for row in rows
    ]


def _group_rows_by_int_field(rows, field_name):
    grouped = {}
    for row in rows:
        field_value = row.get(field_name)
        if field_value in [None, ""]:
            continue
        grouped.setdefault(int(field_value), []).append(dict(row))
    return grouped


def _table_field_spec(info, field_name, default_dtype="float"):
    field_definition = info.get("field_definitions", {}).get(field_name)
    specification = {"name": field_name, "dtype": default_dtype}
    if field_definition is not None:
        specification["field_definition"] = field_definition
    return specification


def _renamed_table_field_spec(info, source_field_name, output_field_name, default_dtype="float"):
    specification = {"name": output_field_name, "dtype": default_dtype}
    field_definition = info.get("field_definitions", {}).get(source_field_name)
    if field_definition is not None:
        specification["field_definition"] = field_definition
    return specification


def _simple_table_field_spec(field_name, dtype):
    return {"name": field_name, "dtype": dtype}


def _empty_input_info():
    return {"records": [], "field_names": [], "field_definitions": {}}


def _build_temp_vector_path(output_reference, base_name, GIStools):
    return _build_temp_path(output_reference, base_name, GIStools)


def _build_temp_table_path(output_reference, base_name, GIStools):
    return _build_temp_path(output_reference, base_name, GIStools)


def _build_temp_path(output_reference, base_name, GIStools):
    unique_name = "{}_{}".format(base_name, uuid.uuid4().hex[:8])
    if _is_qgis(GIStools):
        reference_path = _strip_layer_name(output_reference)
        folder = os.path.dirname(reference_path)
        if folder in [None, ""]:
            folder = os.getcwd()
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, unique_name + ".gpkg")
    return "in_memory\\{}".format(unique_name)


def _strip_layer_name(path):
    path = str(path)
    if "|layername=" in path:
        return path.split("|layername=", 1)[0]
    return path


def _open_vector_dataset(GIStools, dataset, layer_name=None):
    opener = getattr(GIStools.DataManagement, "open_vector_dataset", None)
    if opener is None:
        return dataset
    return opener(dataset, layer_name)


def _is_qgis(GIStools):
    return str(getattr(GIStools, "__name__", "")).lower().endswith("qgistools")


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


def _coerce_reach_orders(network):
    for reach in network.reaches:
        order_value = _as_float(getattr(reach, "order", 0))
        reach.order = 0 if order_value is None else order_value


def _is_true(value):
    if value in [None, "", False]:
        return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ["", "0", "false", "no", "n"]:
            return False
        if normalized in ["1", "true", "yes", "y"]:
            return True
    try:
        return float(value) != 0.0
    except (TypeError, ValueError):
        return bool(value)


def _unique_field_names(field_names):
    unique_names = []
    seen = set()
    for field_name in field_names:
        if field_name in [None, ""]:
            continue
        key = str(field_name).lower()
        if key in seen:
            continue
        seen.add(key)
        unique_names.append(field_name)
    return unique_names


def _make_unique_field_name(base_name, existing_field_names):
    existing_names = {str(field_name).lower() for field_name in existing_field_names if field_name not in [None, ""]}
    suffix = 1
    candidate = base_name
    while str(candidate).lower() in existing_names:
        candidate = "{}_{}".format(base_name, suffix)
        suffix += 1
    return candidate


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


def _add_warning(messages, message):
    if messages is not None:
        messages.add_warning(message)


def _add_error(messages, message):
    if messages is not None:
        messages.add_error(message)
    raise RuntimeError(message)
