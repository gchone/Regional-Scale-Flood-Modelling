from __future__ import annotations

import math
import os

from AssignPointToClosestPointOnRoute import execute_AssignPointToClosestPointOnRoute
from D4FlowDirection import execute_D4FlowDirection
from FlowDirectionNetwork import execute_FlowDirectionNetwork
from InterpolatePoints import execute_InterpolatePoints


TEMP_D4_RID_FIELD = "RID_D4_TMP"


def execute_LisfloodDataConversion(
    lidar10m_fd,
    lidar10m_fill,
    from_pts,
    workspace,
    routes_main,
    routes_main_links,
    routes_RID_field,
    routes_QOrder_field,
    bathy_pts,
    bathy_value_field,
    bathy_RID_field,
    bathy_dist_field,
    width_pts,
    width_value_field,
    width_RID_field,
    width_dist_field,
    d4fd,
    routesD4,
    linksD4,
    pathpointsD4,
    D4fd_net_relatetable,
    bathy_output_raster,
    width_output_raster,
    messages=None,
    GIStools=None,
):
    if GIStools is None:
        GIStools = _autodetect_gistools()

    if workspace not in [None, ""]:
        os.makedirs(str(workspace), exist_ok=True)

    temporary_datasets = []
    try:
        _add_message(messages, "Extracting D4 flow direction network...")
        execute_D4FlowDirection(
            lidar10m_fd,
            lidar10m_fill,
            from_pts,
            d4fd,
            GIStools,
            messages,
        )

        _add_message(messages, "Building D4 river network...")
        execute_FlowDirectionNetwork(
            routes_main,
            routes_main_links,
            routes_RID_field,
            d4fd,
            routesD4,
            linksD4,
            pathpointsD4,
            D4fd_net_relatetable,
            messages=messages,
            GIStools=GIStools,
        )

        relate_table_dataset = _open_vector_dataset(GIStools, D4fd_net_relatetable)
        relate_info = GIStools.DataManagement.read_table_dataset(relate_table_dataset)
        relate_main_field, relate_d4_field = _resolve_relate_fields(
            relate_info["field_names"],
            routes_RID_field,
        )

        _add_message(messages, "Copying Qorder onto the D4 network...")
        GIStools.DataManagement.copy_field_via_relate_table(
            routesD4,
            routes_RID_field,
            relate_table_dataset,
            relate_d4_field,
            relate_main_field,
            routes_main,
            routes_RID_field,
            routes_QOrder_field,
            routes_QOrder_field,
            output_field_dtype="int",
        )

        routesD4_dataset = _open_vector_dataset(GIStools, routesD4)
        linksD4_dataset = _open_vector_dataset(GIStools, linksD4)
        pathpointsD4_dataset = _open_vector_dataset(GIStools, pathpointsD4)

        main_to_d4 = _build_lookup(relate_table_dataset, relate_main_field, relate_d4_field, GIStools)

        _run_lisflood_value_workflow(
            workflow_name="bathymetry",
            input_points=bathy_pts,
            value_field=bathy_value_field,
            input_rid_field=bathy_RID_field,
            input_dist_field=bathy_dist_field,
            assign_stat="MAX",
            routes_main=routes_main,
            routes_RID_field=routes_RID_field,
            routesD4=routesD4_dataset,
            linksD4=linksD4_dataset,
            pathpointsD4=pathpointsD4_dataset,
            routes_QOrder_field=routes_QOrder_field,
            main_to_d4=main_to_d4,
            reference_raster=lidar10m_fd,
            output_raster=bathy_output_raster,
            workspace=workspace,
            GIStools=GIStools,
            messages=messages,
            temporary_datasets=temporary_datasets,
        )

        _run_lisflood_value_workflow(
            workflow_name="width",
            input_points=width_pts,
            value_field=width_value_field,
            input_rid_field=width_RID_field,
            input_dist_field=width_dist_field,
            assign_stat="MEAN",
            routes_main=routes_main,
            routes_RID_field=routes_RID_field,
            routesD4=routesD4_dataset,
            linksD4=linksD4_dataset,
            pathpointsD4=pathpointsD4_dataset,
            routes_QOrder_field=routes_QOrder_field,
            main_to_d4=main_to_d4,
            reference_raster=lidar10m_fd,
            output_raster=width_output_raster,
            workspace=workspace,
            GIStools=GIStools,
            messages=messages,
            temporary_datasets=temporary_datasets,
        )
    finally:
        for dataset_path in reversed(temporary_datasets):
            try:
                GIStools.Geoprocessing.delete_dataset(dataset_path)
            except Exception:
                pass

    return {
        "d4fd": d4fd,
        "routesD4": routesD4,
        "linksD4": linksD4,
        "pathpointsD4": pathpointsD4,
        "D4fd_net_relatetable": D4fd_net_relatetable,
        "bathy_output_raster": bathy_output_raster,
        "width_output_raster": width_output_raster,
    }


def _run_lisflood_value_workflow(
    workflow_name,
    input_points,
    value_field,
    input_rid_field,
    input_dist_field,
    assign_stat,
    routes_main,
    routes_RID_field,
    routesD4,
    linksD4,
    pathpointsD4,
    routes_QOrder_field,
    main_to_d4,
    reference_raster,
    output_raster,
    workspace,
    GIStools,
    messages,
    temporary_datasets,
):
    _add_message(messages, "Processing {}...".format(workflow_name))

    points_on_mainroute = _build_temp_vector_path(workspace, workflow_name + "_on_mainroute", GIStools)
    points_on_mainroute_with_d4 = _build_temp_vector_path(workspace, workflow_name + "_on_mainroute_d4", GIStools)
    assigned_points = _build_temp_vector_path(workspace, workflow_name + "_on_d4", GIStools)
    interpolated_points = _build_temp_vector_path(workspace, workflow_name + "_interpolated", GIStools)
    temporary_datasets.extend(
        [
            points_on_mainroute,
            points_on_mainroute_with_d4,
            assigned_points,
            interpolated_points,
        ]
    )

    _materialize_route_measure_points(
        input_points,
        input_rid_field,
        input_dist_field,
        routes_main,
        routes_RID_field,
        points_on_mainroute,
        GIStools,
        messages,
    )
    _copy_lookup_field_to_points(
        points_on_mainroute,
        input_rid_field,
        TEMP_D4_RID_FIELD,
        main_to_d4,
        points_on_mainroute_with_d4,
        GIStools,
        messages,
    )

    execute_AssignPointToClosestPointOnRoute(
        _open_vector_dataset(GIStools, points_on_mainroute_with_d4),
        [value_field],
        routesD4,
        routes_RID_field,
        pathpointsD4,
        "RID",
        "dist",
        [TEMP_D4_RID_FIELD],
        [routes_RID_field],
        assigned_points,
        stat=assign_stat,
        GIStools=GIStools,
        messages=messages,
    )

    execute_InterpolatePoints(
        _open_vector_dataset(GIStools, assigned_points),
        "id",
        "RID",
        "dist",
        [value_field],
        pathpointsD4,
        "id",
        "RID",
        "dist",
        routesD4,
        linksD4,
        routes_RID_field,
        routes_QOrder_field,
        interpolated_points,
        GIStools=GIStools,
        messages=messages,
    )

    GIStools.Geoprocessing.point_to_raster_most_frequent(
        interpolated_points,
        value_field,
        reference_raster,
        output_raster,
    )
    _add_message(messages, "{} raster written.".format(workflow_name.capitalize()))


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
        _add_warning(messages, "{} record(s) were skipped because their RID was missing from the route network.".format(skipped_missing_route))
    if skipped_missing_measure != 0:
        _add_warning(messages, "{} record(s) were skipped because their measure value was empty or invalid.".format(skipped_missing_measure))

    GIStools.DataManagement.write_bed_assessment_points(
        output_path,
        rows,
        input_info,
        [],
        spatial_reference=spatial_reference,
    )
    _add_message(messages, "Created {} route-event point(s).".format(len(rows)))
    return output_path


def _copy_lookup_field_to_points(input_points, key_field, output_field, lookup, output_path, GIStools, messages):
    point_info = _read_point_dataset_any(GIStools, input_points)
    rows = []
    missing_count = 0
    for row in point_info["records"]:
        output_row = dict(row)
        key_value = row.get(key_field)
        output_row[output_field] = None if key_value in [None, ""] else lookup.get(key_value)
        if output_row[output_field] is None:
            missing_count += 1
        rows.append(output_row)

    GIStools.DataManagement.write_bed_assessment_points(
        output_path,
        rows,
        point_info,
        [{"name": output_field, "dtype": "int"}],
        spatial_reference=point_info.get("spatial_reference"),
    )
    if missing_count != 0:
        _add_warning(messages, "{} route-event point(s) had no D4 relate-table match and will be ignored by the assignment step.".format(missing_count))
    return output_path


def _build_lookup(dataset, key_field, value_field, GIStools):
    info = GIStools.DataManagement.read_table_dataset(dataset, [key_field, value_field])
    lookup = {}
    for row in info["records"]:
        key_value = row.get(key_field)
        value = row.get(value_field)
        if key_value in [None, ""] or value in [None, ""]:
            continue
        if key_value not in lookup:
            lookup[key_value] = value
    return lookup


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
    if measure is None and isinstance(vertex, (list, tuple)) and len(vertex) > 2:
        measure = vertex[2]
    return _as_float(measure)


def _resolve_relate_fields(field_names, main_rid_field):
    candidate_fields = [field_name for field_name in field_names if str(field_name).lower() != "part_count"]
    if len(candidate_fields) < 2:
        raise ValueError("Relate table must contain two route ID fields and PART_COUNT.")

    main_field = None
    for field_name in candidate_fields:
        if str(field_name).lower() == str(main_rid_field).lower():
            main_field = field_name
            break
    if main_field is None:
        main_field = candidate_fields[0]

    d4_field = candidate_fields[1] if candidate_fields[0] == main_field else candidate_fields[0]
    return main_field, d4_field


def _read_point_dataset_any(GIStools, dataset):
    dataset = _open_vector_dataset(GIStools, dataset)
    reader = getattr(GIStools.DataManagement, "read_point_dataset_any", None)
    if reader is None:
        return GIStools.DataManagement.read_point_dataset(dataset)
    return reader(dataset)


def _build_temp_vector_path(workspace, base_name, GIStools):
    extension = ".gpkg" if _is_qgis(GIStools) else ".shp"
    return os.path.join(str(workspace), base_name + extension)


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


def _as_float(value):
    if value in [None, ""]:
        return None
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
