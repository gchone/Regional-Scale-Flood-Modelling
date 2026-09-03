from __future__ import annotations

import math
import os
import uuid

from LocateMostDownstreamPoints import execute_LocateMostDownstreamPoints
from LocatePointsAlongRoutes import execute_LocatePointsAlongRoutes
from TopologicalRelateNetworks import execute_CheckNetFitFromUpStream


def execute_ExtractDischarges(
    routes_Atlas,
    links_Atlas,
    RID_field_Atlas,
    routes_AtlasD8,
    links_AtlasD8,
    RID_field_AtlasD8,
    pts_D8,
    fpoints_atlas,
    routesD8,
    routeD8_RID,
    routes_main,
    route_main_RID,
    relate_table,
    r_flowacc,
    outpoints_D8,
    outpoints_routes,
    GIStools=None,
    messages=None,
):
    if GIStools is None:
        GIStools = _autodetect_gistools()

    routes_Atlas_dataset = _open_vector_dataset(GIStools, routes_Atlas)
    links_Atlas_dataset = _open_vector_dataset(GIStools, links_Atlas)
    routes_AtlasD8_dataset = _open_vector_dataset(GIStools, routes_AtlasD8)
    links_AtlasD8_dataset = _open_vector_dataset(GIStools, links_AtlasD8)
    pts_D8_dataset = _open_vector_dataset(GIStools, pts_D8)
    fpoints_atlas_dataset = _open_vector_dataset(GIStools, fpoints_atlas)
    routesD8_dataset = _open_vector_dataset(GIStools, routesD8)
    routes_main_dataset = _open_vector_dataset(GIStools, routes_main)
    relate_table_dataset = _open_vector_dataset(GIStools, relate_table)

    temporary_datasets = []
    try:
        _add_message(messages, "Creating Atlas D8-to-Atlas crosswalk...")
        matchatlas = _build_temp_table_path(outpoints_D8, "extractdischarges_matchatlas", GIStools)
        temporary_datasets.append(matchatlas)
        execute_CheckNetFitFromUpStream(
            routes_AtlasD8_dataset,
            links_AtlasD8_dataset,
            RID_field_AtlasD8,
            routes_Atlas_dataset,
            links_Atlas_dataset,
            RID_field_Atlas,
            fpoints_atlas_dataset,
            matchatlas,
            messages=messages,
            final_selection="ENDS",
            GIStools=GIStools,
        )

        _add_message(messages, "Locating most-downstream Atlas D8 path points...")
        qpoints_d8 = _build_temp_vector_path(outpoints_D8, "extractdischarges_qptsd8", GIStools)
        temporary_datasets.append(qpoints_d8)
        execute_LocateMostDownstreamPoints(
            routes_AtlasD8_dataset,
            links_AtlasD8_dataset,
            RID_field_AtlasD8,
            pts_D8_dataset,
            "id",
            "RID",
            "dist",
            "X",
            "Y",
            qpoints_d8,
            GIStools=GIStools,
            messages=messages,
        )

        _add_message(messages, "Snapping downstream points to the nearest D8 routes...")
        snapped_info = GIStools.Geoprocessing.snap_points_to_nearest_line(
            _open_vector_dataset(GIStools, qpoints_d8),
            routesD8_dataset,
            field_names=[routeD8_RID],
            tolerance=0.1,
        )
        if len(snapped_info["records"]) == 0:
            _add_error(messages, "No downstream D8 points were found within 0.1 units of the supplied D8 routes.")

        _add_message(messages, "Sampling flow accumulation at snapped D8 points...")
        sampled_info = GIStools.Geoprocessing.sample_raster_at_points(
            snapped_info,
            r_flowacc,
            "flowacc",
        )

        pts_d8_info = GIStools.DataManagement.read_table_dataset(
            pts_D8_dataset,
            ["id", RID_field_AtlasD8],
        )
        matchatlas_dataset = _open_vector_dataset(GIStools, matchatlas)
        matchatlas_info = GIStools.DataManagement.read_table_dataset(matchatlas_dataset)
        relate_info = GIStools.DataManagement.read_table_dataset(relate_table_dataset)
        matchatlas_d8_field, matchatlas_match_field = _resolve_matchatlas_fields(
            matchatlas_info["field_names"],
            RID_field_AtlasD8,
        )
        relate_main_field, relate_d8_field = _resolve_relate_fields(
            relate_info["field_names"],
            routeD8_RID,
            route_main_RID,
        )

        point_to_atlasd8 = _build_lookup(pts_d8_info["records"], "id", RID_field_AtlasD8)
        matchatlas_by_d8 = _build_row_lookup(matchatlas_info["records"], matchatlas_d8_field)
        main_rid_by_d8 = _build_lookup(relate_info["records"], relate_d8_field, relate_main_field)

        raster_grid = GIStools.RasterAccess.read_raster_grid(r_flowacc)
        cell_area = float(raster_grid["pixel_width"]) * float(raster_grid["pixel_height"])

        output_rows = []
        missing_atlas_rids = 0
        missing_matchatlas = 0
        missing_main_route = 0
        for row in sampled_info["records"]:
            atlasd8_rid = point_to_atlasd8.get(row.get("id"))
            if atlasd8_rid is None:
                missing_atlas_rids += 1

            match_row = None if atlasd8_rid is None else matchatlas_by_d8.get(atlasd8_rid)
            if atlasd8_rid is not None and match_row is None:
                missing_matchatlas += 1

            d8_rid = row.get(routeD8_RID)
            main_rid = None if d8_rid in [None, ""] else main_rid_by_d8.get(d8_rid)
            if d8_rid not in [None, ""] and main_rid is None:
                missing_main_route += 1

            flowacc_value = _as_float(row.get("flowacc"))
            output_rows.append(
                {
                    "X": row.get("X"),
                    "Y": row.get("Y"),
                    route_main_RID: main_rid,
                    "MATCH_ID": None if match_row is None else match_row.get(matchatlas_match_field),
                    "Flowacc": flowacc_value,
                    "TYPO": None if match_row is None else match_row.get("TYPO"),
                    "CLOSEST": None if match_row is None else match_row.get("CLOSEST"),
                    "SCORE": None if match_row is None else match_row.get("SCORE"),
                    "Drainage": None if flowacc_value is None else cell_area * flowacc_value / 1000000.0,
                }
            )

        if missing_atlas_rids != 0:
            _add_warning(
                messages,
                "{} snapped point(s) could not be matched back to the source Atlas D8 RID field.".format(
                    missing_atlas_rids
                ),
            )
        if missing_matchatlas != 0:
            _add_warning(
                messages,
                "{} snapped point(s) had no Atlas-route match in the topological relate table.".format(
                    missing_matchatlas
                ),
            )
        if missing_main_route != 0:
            _add_warning(
                messages,
                "{} snapped point(s) had no D8-to-main-network relate-table match.".format(
                    missing_main_route
                ),
            )

        _add_message(messages, "Writing D8 discharge extraction points...")
        GIStools.DataManagement.write_bed_assessment_points(
            outpoints_D8,
            output_rows,
            _empty_input_info(),
            [
                {
                    "name": route_main_RID,
                    "dtype": _infer_simple_dtype((row.get(route_main_RID) for row in output_rows), default="int"),
                },
                {
                    "name": "MATCH_ID",
                    "dtype": _infer_simple_dtype((row.get("MATCH_ID") for row in output_rows), default="int"),
                },
                {"name": "Flowacc", "dtype": "float"},
                {"name": "TYPO", "dtype": "float"},
                {
                    "name": "CLOSEST",
                    "dtype": _infer_simple_dtype((row.get("CLOSEST") for row in output_rows), default="int"),
                },
                {"name": "SCORE", "dtype": "float"},
                {"name": "Drainage", "dtype": "float"},
            ],
            spatial_reference=sampled_info.get("spatial_reference"),
        )

        _add_message(messages, "Locating extracted discharges along the main routes...")
        res_table = _build_temp_table_path(outpoints_routes, "extractdischarges_res", GIStools)
        temporary_datasets.append(res_table)
        execute_LocatePointsAlongRoutes(
            _open_vector_dataset(GIStools, outpoints_D8),
            route_main_RID,
            routes_main_dataset,
            route_main_RID,
            res_table,
            10000,
            GIStools=GIStools,
            messages=messages,
        )

        _add_message(messages, "Materializing main-route discharge points...")
        _materialize_route_measure_points(
            _open_vector_dataset(GIStools, res_table),
            route_main_RID,
            "MEAS",
            routes_main_dataset,
            route_main_RID,
            outpoints_routes,
            GIStools,
            messages,
        )
    finally:
        for dataset_path in reversed(temporary_datasets):
            try:
                GIStools.Geoprocessing.delete_dataset(dataset_path)
            except Exception:
                pass

    return {
        "outpoints_D8": outpoints_D8,
        "outpoints_routes": outpoints_routes,
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


def _resolve_matchatlas_fields(field_names, d8_rid_field):
    auxiliary_fields = {"TYPO", "CLOSEST", "SCORE", "PART_COUNT"}
    candidate_fields = [field_name for field_name in field_names if str(field_name).upper() not in auxiliary_fields]
    if len(candidate_fields) < 2:
        raise ValueError("Topological relate table must contain the Atlas D8 RID field and MATCH_ID.")

    d8_field = None
    for field_name in candidate_fields:
        if str(field_name).lower() == str(d8_rid_field).lower():
            d8_field = field_name
            break
    if d8_field is None:
        d8_field = candidate_fields[0]

    match_field = None
    for field_name in candidate_fields:
        if str(field_name).upper() == "MATCH_ID":
            match_field = field_name
            break
    if match_field is None:
        for field_name in candidate_fields:
            if field_name != d8_field:
                match_field = field_name
                break
    if match_field is None:
        raise ValueError("Topological relate-table MATCH_ID field could not be resolved.")
    return d8_field, match_field


def _resolve_relate_fields(field_names, d8_rid_field, main_rid_field):
    candidate_fields = [field_name for field_name in field_names if str(field_name).lower() != "part_count"]
    if len(candidate_fields) < 2:
        raise ValueError("Relate table must contain two route ID fields and PART_COUNT.")

    d8_field = None
    for field_name in candidate_fields:
        if str(field_name).lower() == str(d8_rid_field).lower():
            d8_field = field_name
            break

    main_field = None
    for field_name in candidate_fields:
        if str(field_name).lower() == str(main_rid_field).lower():
            main_field = field_name
            break

    if d8_field is None and main_field is not None:
        d8_field = candidate_fields[1] if candidate_fields[0] == main_field else candidate_fields[0]
    if d8_field is None:
        d8_field = candidate_fields[-1]

    if main_field is None:
        for field_name in candidate_fields:
            if field_name != d8_field:
                main_field = field_name
                break
    if main_field is None:
        raise ValueError("Main-network RID field could not be resolved from the relate table.")
    return main_field, d8_field


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


def _build_row_lookup(rows, key_field):
    lookup = {}
    for row in rows:
        key_value = row.get(key_field)
        if key_value in [None, ""] or key_value in lookup:
            continue
        lookup[key_value] = dict(row)
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
