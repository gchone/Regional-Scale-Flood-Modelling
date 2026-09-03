import math


SUPPORTED_STATS = ["MEAN", "CLOSEST", "MAX", "2-WAY CLOSEST"]


def execute_AssignPointToClosestPointOnRoute(points, list_fields_to_keep, routes, routes_IDfield,
                                             points_onroute, points_onroute_RIDfield, points_onroute_distfield,
                                             matching_fields_pts, matching_fields_targetpts, output_shp, stat="MEAN",
                                             GIStools=None, messages=None):

    if GIStools is None:
        raise ValueError("A GIStools package must be provided.")

    list_fields_to_keep = _normalize_field_names(list_fields_to_keep, deduplicate=True)
    matching_fields_pts = _normalize_field_names(matching_fields_pts)
    matching_fields_targetpts = _normalize_field_names(matching_fields_targetpts)
    stat = str(stat or "MEAN").upper()

    if stat not in SUPPORTED_STATS:
        _add_error(messages, f"Unsupported stat '{stat}'. Expected one of {SUPPORTED_STATS}.")
    if len(matching_fields_pts) != len(matching_fields_targetpts):
        _add_error(messages, "The data-point matching fields and target-point matching fields must have the same length.")

    prepared_points_onroute = GIStools.Geoprocessing.create_points_on_route_layer(
        routes,
        routes_IDfield,
        points_onroute,
        points_onroute_RIDfield,
        points_onroute_distfield,
    )

    try:
        data_fields_to_read = _unique_field_names(list_fields_to_keep + matching_fields_pts)
        data_info = GIStools.DataManagement.read_point_dataset(points, data_fields_to_read)
        target_info = GIStools.DataManagement.read_point_dataset(prepared_points_onroute)

        route_geometries = {}
        if stat == "2-WAY CLOSEST":
            route_geometries = GIStools.DataManagement.read_route_geometries(routes, routes_IDfield)

        _add_message(
            messages,
            f"Loaded {len(data_info['records'])} data point(s) and {len(target_info['records'])} target point(s).",
        )

        results = assign_point_to_closest_point_on_route(
            data_points=data_info["records"],
            data_fields=list_fields_to_keep,
            data_matching_fields=matching_fields_pts,
            target_points=target_info["records"],
            target_rid_field=points_onroute_RIDfield,
            target_dist_field=points_onroute_distfield,
            target_matching_fields=matching_fields_targetpts,
            routes=route_geometries,
            stat=stat,
            messages=messages,
        )

        if len(results) == 0:
            _add_warning(messages, "No matching points were found; the output will be empty.")

        return GIStools.DataManagement.write_output_points(
            output_shp,
            results,
            target_info,
            data_info,
            list_fields_to_keep,
            include_near_dist=(stat != "CLOSEST"),
        )
    except Exception as exc:
        _add_error(messages, str(exc))
    finally:
        try:
            GIStools.Geoprocessing.delete_layer(prepared_points_onroute)
        except Exception:
            pass


def assign_point_to_closest_point_on_route(data_points, data_fields, data_matching_fields,
                                           target_points, target_rid_field, target_dist_field,
                                           target_matching_fields, routes=None, stat="MEAN", messages=None):

    data_by_match = _group_records_by_match(data_points, data_matching_fields)
    target_by_match = _group_records_by_match(target_points, target_matching_fields)
    common_matches = _ordered_common_match_keys(data_points, data_matching_fields, target_by_match)

    _add_message(messages, f"Found {len(common_matches)} matching group(s).")

    if stat == "CLOSEST":
        results = _assign_closest(data_fields, common_matches, data_by_match, target_by_match)
    elif stat == "2-WAY CLOSEST":
        results = _assign_two_way_closest(
            data_fields,
            target_rid_field,
            target_dist_field,
            common_matches,
            data_by_match,
            target_by_match,
            routes or {},
            messages,
        )
    else:
        results = _assign_mean_or_max(stat, data_fields, common_matches, data_by_match, target_by_match)

    _add_message(messages, f"Assigned values to {len(results)} target point(s).")
    return results


def _assign_mean_or_max(stat, data_fields, common_matches, data_by_match, target_by_match):
    results = []

    for match_key in common_matches:
        data_records = data_by_match.get(match_key, [])
        target_records = target_by_match.get(match_key, [])
        target_assignments = {}

        for data_record in data_records:
            closest_target, near_dist = _find_closest_record(data_record, target_records)
            if closest_target is None:
                continue
            target_id = closest_target["_oid"]
            if target_id not in target_assignments:
                target_assignments[target_id] = {
                    "target": closest_target,
                    "data_records": [],
                    "near_dist": near_dist,
                }
            target_assignments[target_id]["data_records"].append(data_record)

        for target_record in target_records:
            assignment = target_assignments.get(target_record["_oid"])
            if assignment is None:
                continue
            result = _copy_target_record(assignment["target"])
            for field_name in data_fields:
                result[field_name] = _aggregate_numeric_field(assignment["data_records"], field_name, stat)
            result["NEAR_DIST"] = assignment["near_dist"]
            results.append(result)

    return results


def _assign_closest(data_fields, common_matches, data_by_match, target_by_match):
    results = []

    for match_key in common_matches:
        data_records = data_by_match.get(match_key, [])
        target_records = target_by_match.get(match_key, [])

        for target_record in target_records:
            closest_data, near_dist = _find_closest_record(target_record, data_records)
            result = _copy_target_record(target_record)
            for field_name in data_fields:
                result[field_name] = None if closest_data is None else closest_data.get(field_name)
            if near_dist is not None:
                result["_closest_distance"] = near_dist
            results.append(result)

    return results


def _assign_two_way_closest(data_fields, target_rid_field, target_dist_field, common_matches,
                            data_by_match, target_by_match, routes, messages):
    results = []
    missing_routes = set()
    invalid_measures = set()

    for match_key in common_matches:
        data_records = data_by_match.get(match_key, [])
        target_records = target_by_match.get(match_key, [])
        route_measure_cache = {}

        for target_record in target_records:
            rid = target_record.get(target_rid_field)
            target_measure = _as_float(target_record.get(target_dist_field))
            closest_data = None
            near_dist = None

            if target_measure is None:
                invalid_measures.add(rid)
            else:
                if rid not in route_measure_cache:
                    route_parts = routes.get(rid)
                    if route_parts is None:
                        missing_routes.add(rid)
                        route_measure_cache[rid] = []
                    else:
                        route_measure_cache[rid] = [
                            (_measure_point_along_route(data_record, route_parts), data_record)
                            for data_record in data_records
                        ]

                for data_measure, data_record in route_measure_cache.get(rid, []):
                    if data_measure is None:
                        continue
                    distance_on_route = abs(data_measure - target_measure)
                    if closest_data is None or distance_on_route < near_dist:
                        closest_data = data_record
                        near_dist = distance_on_route

            if closest_data is None:
                closest_data, near_dist = _find_closest_record(target_record, data_records)

            result = _copy_target_record(target_record)
            for field_name in data_fields:
                result[field_name] = None if closest_data is None else closest_data.get(field_name)
            result["NEAR_DIST"] = near_dist
            results.append(result)

    for rid in sorted(missing_routes, key=lambda value: str(value)):
        _add_warning(messages, f"Route '{rid}' was not found; 2-WAY CLOSEST fell back to point distance for that route.")
    for rid in sorted(invalid_measures, key=lambda value: str(value)):
        _add_warning(messages, f"Route-measure values are missing or invalid for route '{rid}'; 2-WAY CLOSEST fell back to point distance.")

    return results


def _group_records_by_match(records, field_names):
    grouped_records = {}
    for record in records:
        match_key = _build_match_key(record, field_names)
        if match_key not in grouped_records:
            grouped_records[match_key] = []
        grouped_records[match_key].append(record)
    return grouped_records


def _ordered_common_match_keys(data_points, data_matching_fields, target_by_match):
    common_matches = []
    seen_keys = set()
    for record in data_points:
        match_key = _build_match_key(record, data_matching_fields)
        if match_key in target_by_match and match_key not in seen_keys:
            seen_keys.add(match_key)
            common_matches.append(match_key)
    return common_matches


def _build_match_key(record, field_names):
    return tuple(record.get(field_name) for field_name in field_names)


def _find_closest_record(source_record, candidate_records):
    closest_record = None
    closest_distance = None

    for candidate_record in candidate_records:
        distance = _euclidean_distance(source_record, candidate_record)
        if closest_record is None or distance < closest_distance:
            closest_record = candidate_record
            closest_distance = distance

    return closest_record, closest_distance


def _euclidean_distance(point_a, point_b):
    return math.hypot(float(point_a["X"]) - float(point_b["X"]), float(point_a["Y"]) - float(point_b["Y"]))


def _measure_point_along_route(point_record, route_parts):
    point_x = float(point_record["X"])
    point_y = float(point_record["Y"])
    best_distance = None
    best_measure = None
    cumulative_length = 0.0

    for part in route_parts:
        if len(part) == 1:
            distance = math.hypot(point_x - float(part[0][0]), point_y - float(part[0][1]))
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_measure = cumulative_length
            continue

        for start_point, end_point in zip(part[:-1], part[1:]):
            start_x = float(start_point[0])
            start_y = float(start_point[1])
            end_x = float(end_point[0])
            end_y = float(end_point[1])
            delta_x = end_x - start_x
            delta_y = end_y - start_y
            segment_length_sq = delta_x * delta_x + delta_y * delta_y
            segment_length = math.sqrt(segment_length_sq)

            if segment_length_sq == 0:
                ratio = 0.0
                projected_x = start_x
                projected_y = start_y
            else:
                ratio = ((point_x - start_x) * delta_x + (point_y - start_y) * delta_y) / segment_length_sq
                ratio = max(0.0, min(1.0, ratio))
                projected_x = start_x + ratio * delta_x
                projected_y = start_y + ratio * delta_y

            distance = math.hypot(point_x - projected_x, point_y - projected_y)
            measure = cumulative_length + ratio * segment_length

            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_measure = measure

            cumulative_length += segment_length

    return best_measure


def _aggregate_numeric_field(records, field_name, stat):
    values = []
    for record in records:
        value = record.get(field_name)
        if value is None:
            continue
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            raise ValueError(f"Field '{field_name}' must contain numeric values for '{stat}'.")

    if len(values) == 0:
        return None
    if stat == "MEAN":
        return sum(values) / float(len(values))
    return max(values)


def _copy_target_record(target_record):
    copied_record = {"X": target_record.get("X"), "Y": target_record.get("Y")}
    for key, value in target_record.items():
        if key in ["X", "Y", "_oid"]:
            continue
        copied_record[key] = value
    return copied_record


def _normalize_field_names(field_names, deduplicate=False):
    if field_names is None:
        return []
    if isinstance(field_names, str):
        field_names = field_names.split(";")

    normalized_fields = []
    for field_name in field_names:
        if field_name is None:
            continue
        normalized_name = str(field_name).strip()
        if normalized_name == "":
            continue
        normalized_name = normalized_name.split(".")[-1]
        if not deduplicate or normalized_name not in normalized_fields:
            normalized_fields.append(normalized_name)
    return normalized_fields


def _unique_field_names(field_names):
    unique_names = []
    for field_name in field_names:
        if field_name not in unique_names:
            unique_names.append(field_name)
    return unique_names


def _as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _add_message(messages, message):
    if messages is not None:
        messages.add_message(message)


def _add_warning(messages, message):
    if messages is not None:
        messages.add_warning(message)


def _add_error(messages, message):
    if messages is not None:
        messages.add_error(message)
    raise ValueError(message)
