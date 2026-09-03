from __future__ import annotations

import math
import os
import uuid

from AssignPointToClosestPointOnRoute import execute_AssignPointToClosestPointOnRoute
from InterpolatePoints import execute_InterpolatePoints
from TopologicalRelateNetworks import execute_CheckNetFitFromUpStream
from WSsmoothing import execute_WSprocessing


def execute_ExtractWaterSurface(
    routes,
    links,
    RID_field,
    order_field,
    frompoints,
    routes_3m,
    RID_field_3m,
    links_3m,
    pts_table,
    X_field_pts,
    Y_field_pts,
    lidar3m_cor,
    DEMs_footprints,
    DEMs_field,
    pts_bathy,
    pts_bathy_ID_field,
    pts_bathy_RID_field,
    pts_bathy_dist_field,
    relatetable,
    ouput_table,
    GIStools=None,
    messages=None,
):
    if GIStools is None:
        GIStools = _autodetect_gistools()

    routes_dataset = _open_vector_dataset(GIStools, routes)
    links_dataset = _open_vector_dataset(GIStools, links)
    frompoints_dataset = _open_vector_dataset(GIStools, frompoints)
    routes_3m_dataset = _open_vector_dataset(GIStools, routes_3m)
    links_3m_dataset = _open_vector_dataset(GIStools, links_3m)
    pts_table_dataset = _open_vector_dataset(GIStools, pts_table)
    pts_bathy_dataset = _open_vector_dataset(GIStools, pts_bathy)
    dems_footprints_dataset = _open_vector_dataset(GIStools, DEMs_footprints)

    ws_field_name = _raster_field_name(lidar3m_cor)
    temporary_datasets = []

    try:
        _add_message(messages, "Creating D8-to-main-network relate table...")
        execute_CheckNetFitFromUpStream(
            routes_3m_dataset,
            links_3m_dataset,
            RID_field_3m,
            routes_dataset,
            links_dataset,
            RID_field,
            frompoints_dataset,
            relatetable,
            messages=messages,
            final_selection="ENDS",
            GIStools=GIStools,
        )

        relate_dataset = _open_vector_dataset(GIStools, relatetable)
        relate_info = GIStools.DataManagement.read_table_dataset(relate_dataset)
        relate_d8_field, relate_main_field = _resolve_topological_relate_fields(
            relate_info["field_names"],
            RID_field_3m,
        )
        d8_to_main = _build_lookup(relate_info["records"], relate_d8_field, relate_main_field)

        _add_message(messages, "Materializing target points from route measures...")
        materialized_targets = _build_temp_vector_path(ouput_table, "extractws_targets", GIStools)
        temporary_datasets.append(materialized_targets)
        _materialize_route_measure_points(
            pts_bathy_dataset,
            pts_bathy_RID_field,
            pts_bathy_dist_field,
            routes_dataset,
            RID_field,
            materialized_targets,
            GIStools,
            messages,
        )
        materialized_targets_dataset = _open_vector_dataset(GIStools, materialized_targets)

        _add_message(messages, "Sampling corrected DEM at D8 path points...")
        pathpoint_info = GIStools.DataManagement.read_table_dataset(
            pts_table_dataset,
            _unique_field_names([RID_field_3m, X_field_pts, Y_field_pts]),
        )
        pathpoint_info = _prepare_xy_sample_info(
            pathpoint_info,
            X_field_pts,
            Y_field_pts,
            GIStools.DataManagement.get_spatial_reference(routes_3m_dataset),
        )
        sampled_pathpoints_info = GIStools.Geoprocessing.sample_raster_at_points(
            pathpoint_info,
            lidar3m_cor,
            ws_field_name,
        )

        missing_match_count = 0
        for row in sampled_pathpoints_info["records"]:
            d8_rid = row.get(RID_field_3m)
            main_rid = None if d8_rid in [None, ""] else d8_to_main.get(d8_rid)
            row[pts_bathy_RID_field] = main_rid
            if main_rid is None:
                missing_match_count += 1

        if len(sampled_pathpoints_info["records"]) == 0:
            _add_error(messages, "No D8 path points were available for raster sampling.")
        if missing_match_count != 0:
            _add_warning(
                messages,
                "{} sampled D8 path point(s) had no relate-table match to the main network and will be ignored.".format(
                    missing_match_count
                ),
            )

        sampled_pathpoints = _build_temp_vector_path(ouput_table, "extractws_pathpoints", GIStools)
        temporary_datasets.append(sampled_pathpoints)
        GIStools.DataManagement.write_bed_assessment_points(
            sampled_pathpoints,
            sampled_pathpoints_info["records"],
            pathpoint_info,
            [
                {"name": ws_field_name, "dtype": "float"},
                {"name": pts_bathy_RID_field, "dtype": _infer_simple_dtype(d8_to_main.values(), default="int")},
            ],
            spatial_reference=sampled_pathpoints_info.get("spatial_reference"),
        )

        _add_message(messages, "Assigning sampled D8 elevations to target points...")
        assigned_points = _build_temp_vector_path(ouput_table, "extractws_assigned", GIStools)
        temporary_datasets.append(assigned_points)
        execute_AssignPointToClosestPointOnRoute(
            _open_vector_dataset(GIStools, sampled_pathpoints),
            [ws_field_name],
            routes_dataset,
            RID_field,
            materialized_targets_dataset,
            pts_bathy_RID_field,
            pts_bathy_dist_field,
            [pts_bathy_RID_field],
            [pts_bathy_RID_field],
            assigned_points,
            stat="2-WAY CLOSEST",
            GIStools=GIStools,
            messages=messages,
        )

        _add_message(messages, "Interpolating water surface along the main network...")
        interpolated_points = _build_temp_vector_path(ouput_table, "extractws_interpolated", GIStools)
        temporary_datasets.append(interpolated_points)
        execute_InterpolatePoints(
            _open_vector_dataset(GIStools, assigned_points),
            pts_bathy_ID_field,
            pts_bathy_RID_field,
            pts_bathy_dist_field,
            [ws_field_name],
            materialized_targets_dataset,
            pts_bathy_ID_field,
            pts_bathy_RID_field,
            pts_bathy_dist_field,
            routes_dataset,
            links_dataset,
            RID_field,
            order_field,
            interpolated_points,
            GIStools=GIStools,
            messages=messages,
        )

        _add_message(messages, "Joining DEM footprint identifiers onto interpolated points...")
        interpolated_with_dem_info = GIStools.Geoprocessing.join_polygon_field_to_points_records(
            _open_vector_dataset(GIStools, interpolated_points),
            dems_footprints_dataset,
            DEMs_field,
            field_names=[pts_bathy_ID_field, pts_bathy_RID_field, pts_bathy_dist_field, ws_field_name],
        )
        if len(interpolated_with_dem_info["records"]) == 0:
            _add_error(messages, "No interpolated points were produced.")

        interpolated_with_dem = _build_temp_vector_path(ouput_table, "extractws_interpdem", GIStools)
        temporary_datasets.append(interpolated_with_dem)
        GIStools.DataManagement.write_bed_assessment_points(
            interpolated_with_dem,
            interpolated_with_dem_info["records"],
            interpolated_with_dem_info,
            [],
            spatial_reference=interpolated_with_dem_info.get("spatial_reference"),
        )

        _add_message(messages, "Applying water-surface smoothing...")
        execute_WSprocessing(
            routes_dataset,
            links_dataset,
            RID_field,
            order_field,
            _open_vector_dataset(GIStools, interpolated_with_dem),
            pts_bathy_ID_field,
            pts_bathy_RID_field,
            pts_bathy_dist_field,
            ws_field_name,
            DEMs_field,
            ouput_table,
            GIStools=GIStools,
            messages=messages,
        )
    finally:
        for dataset_path in reversed(temporary_datasets):
            try:
                GIStools.Geoprocessing.delete_dataset(dataset_path)
            except Exception:
                pass

    return {
        "relatetable": relatetable,
        "ouput_table": ouput_table,
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
    if callable(measure):
        measure = measure()
    if measure is None and isinstance(vertex, (list, tuple)) and len(vertex) > 2:
        measure = vertex[2]
    return _as_float(measure)


def _prepare_xy_sample_info(input_info, x_field_name, y_field_name, spatial_reference):
    prepared_info = {
        "records": [],
        "field_names": list(input_info.get("field_names", [])),
        "field_definitions": dict(input_info.get("field_definitions", {})),
        "spatial_reference": input_info.get("spatial_reference", spatial_reference),
    }
    if prepared_info["spatial_reference"] is None:
        prepared_info["spatial_reference"] = spatial_reference

    for row in input_info["records"]:
        prepared_row = dict(row)
        prepared_row["X"] = _as_float(row.get(x_field_name, row.get("X")))
        prepared_row["Y"] = _as_float(row.get(y_field_name, row.get("Y")))
        prepared_info["records"].append(prepared_row)
    return prepared_info


def _resolve_topological_relate_fields(field_names, d8_rid_field):
    auxiliary_fields = {"TYPO", "CLOSEST", "SCORE", "PART_COUNT"}
    candidate_fields = [field_name for field_name in field_names if str(field_name).upper() not in auxiliary_fields]
    if len(candidate_fields) < 2:
        raise ValueError("Relate table must contain the D8 RID field and a main-network match field.")

    d8_field = None
    for field_name in candidate_fields:
        if str(field_name).lower() == str(d8_rid_field).lower():
            d8_field = field_name
            break
    if d8_field is None:
        d8_field = candidate_fields[0]

    main_field = None
    for field_name in candidate_fields:
        if str(field_name).upper() == "MATCH_ID":
            main_field = field_name
            break
    if main_field is None:
        for field_name in candidate_fields:
            if field_name != d8_field:
                main_field = field_name
                break
    if main_field is None:
        raise ValueError("Relate table match field could not be resolved.")
    return d8_field, main_field


def _build_lookup(rows, key_field, value_field):
    lookup = {}
    for row in rows:
        key_value = row.get(key_field)
        value = row.get(value_field)
        if key_value in [None, ""] or value in [None, ""]:
            continue
        if key_value not in lookup:
            lookup[key_value] = value
    return lookup


def _infer_simple_dtype(values, default="float"):
    for value in values:
        if value in [None, ""]:
            continue
        if isinstance(value, str):
            return "str"
        if isinstance(value, bool):
            return "int"
        if isinstance(value, int):
            return "int"
        if isinstance(value, float):
            return "int" if float(value).is_integer() else "float"
    return default


def _unique_field_names(field_names):
    unique_names = []
    seen = set()
    for field_name in field_names:
        if field_name in [None, ""]:
            continue
        if field_name in seen:
            continue
        seen.add(field_name)
        unique_names.append(field_name)
    return unique_names


def _build_temp_vector_path(output_reference, base_name, GIStools):
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


def _raster_field_name(raster):
    raster_path = None
    if hasattr(raster, "source"):
        try:
            raster_path = raster.source()
        except Exception:
            raster_path = None
    if raster_path in [None, ""] and hasattr(raster, "catalogPath"):
        raster_path = raster.catalogPath
    if raster_path in [None, ""]:
        raster_path = str(raster)
    raster_path = _strip_layer_name(raster_path)
    basename = os.path.basename(str(raster_path))
    field_name, extension = os.path.splitext(basename)
    if extension == "" and basename not in [None, ""]:
        field_name = basename
    if field_name in [None, ""]:
        field_name = "raster_value"
    return field_name


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
