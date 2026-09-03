import math


def execute_LocatePointsAlongRoutes(
    points,
    points_RIDfield,
    routes,
    routes_RIDfield,
    output,
    distance,
    GIStools=None,
    messages=None,
):
    if GIStools is None:
        GIStools = _autodetect_gistools()

    try:
        distance_value = float(distance)
        if distance_value < 0:
            raise ValueError("Searching distance must be greater than or equal to 0.")

        points_info = _read_point_dataset(GIStools, points)
        route_info = GIStools.DataManagement.read_table_dataset(routes, [routes_RIDfield])
        route_features = list(GIStools.DataManagement.load_line_features(routes, [routes_RIDfield]))

        rid_field_name, add_rid_field, meas_field_name, rename_notes = _resolve_output_field_names(
            points_info["field_names"],
            points_RIDfield,
            routes_RIDfield,
        )
        for note in rename_notes:
            _add_warning(messages, note)

        _add_message(
            messages,
            "Loaded {} point(s) and {} route feature(s).".format(
                len(points_info["records"]),
                len(route_features),
            ),
        )

        output_rows = locate_points_along_routes(
            points,
            points_RIDfield,
            routes,
            routes_RIDfield,
            distance_value,
            GIStools=GIStools,
            messages=messages,
            preloaded_points_info=points_info,
            preloaded_route_features=route_features,
            output_rid_field=rid_field_name,
            output_meas_field=meas_field_name,
        )

        _add_message(
            messages,
            "Located {} point-to-route match(es).".format(len(output_rows)),
        )
        if len(output_rows) == 0:
            _add_warning(messages, "No points were found within the searching distance of their matching route feature(s).")

        if output is None:
            return output_rows

        extra_fields = []
        if add_rid_field:
            extra_fields.append(
                {
                    "name": rid_field_name,
                    "field_definition": route_info["field_definitions"].get(routes_RIDfield),
                    "dtype": "int",
                }
            )
        extra_fields.append({"name": meas_field_name, "dtype": "float"})

        return GIStools.DataManagement.write_output_table(
            output,
            output_rows,
            points_info,
            extra_fields,
        )
    except Exception as exc:
        if messages is None:
            raise
        _add_error(messages, str(exc))


def locate_points_along_routes(
    points,
    points_rid_field,
    routes,
    routes_rid_field,
    distance=10000.0,
    GIStools=None,
    messages=None,
    preloaded_points_info=None,
    preloaded_route_features=None,
    output_rid_field=None,
    output_meas_field=None,
):
    if GIStools is None:
        GIStools = _autodetect_gistools()

    points_info = preloaded_points_info
    if points_info is None:
        points_info = _read_point_dataset(GIStools, points)

    route_features = preloaded_route_features
    if route_features is None:
        route_features = list(GIStools.DataManagement.load_line_features(routes, [routes_rid_field]))

    rid_field_name = output_rid_field
    meas_field_name = output_meas_field
    if rid_field_name is None or meas_field_name is None:
        rid_field_name, _, meas_field_name, rename_notes = _resolve_output_field_names(
            points_info["field_names"],
            points_rid_field,
            routes_rid_field,
        )
        for note in rename_notes:
            _add_warning(messages, note)

    return locate_points_along_route_rows(
        points_info["records"],
        points_rid_field,
        route_features,
        routes_rid_field,
        float(distance),
        rid_field_name,
        meas_field_name,
    )


def locate_points_along_route_rows(
    point_records,
    points_rid_field,
    route_features,
    routes_rid_field,
    distance,
    output_rid_field,
    output_meas_field="MEAS",
):
    points_by_rid = _group_points_by_rid(point_records, points_rid_field)
    output_rows = []

    for route_feature in route_features:
        rid_value = route_feature.attributes.get(routes_rid_field)
        if rid_value is None:
            continue

        matching_points = points_by_rid.get(rid_value, [])
        if len(matching_points) == 0:
            continue

        for point_row in matching_points:
            point_x = _as_float(point_row.get("X"))
            point_y = _as_float(point_row.get("Y"))
            if point_x is None or point_y is None:
                continue

            locate_result = _locate_point_on_line(point_x, point_y, route_feature)
            if locate_result is None:
                continue

            snap_distance, measure = locate_result
            if snap_distance > distance:
                continue

            output_row = dict(point_row)
            output_row[output_rid_field] = rid_value
            output_row[output_meas_field] = measure
            output_rows.append(output_row)

    return output_rows


def _group_points_by_rid(point_records, rid_field_name):
    grouped = {}
    for row in point_records:
        rid_value = row.get(rid_field_name)
        if rid_value is None:
            continue
        grouped.setdefault(rid_value, []).append(row)
    return grouped


def _locate_point_on_line(point_x, point_y, route_feature):
    best_distance = None
    best_measure = None
    accumulated_length = 0.0

    for start_point, end_point in zip(route_feature.vertices[:-1], route_feature.vertices[1:]):
        dx = float(end_point.x) - float(start_point.x)
        dy = float(end_point.y) - float(start_point.y)
        segment_length = math.hypot(dx, dy)
        if segment_length == 0:
            continue

        ratio = ((point_x - float(start_point.x)) * dx + (point_y - float(start_point.y)) * dy) / (segment_length * segment_length)
        ratio = max(0.0, min(1.0, ratio))

        projected_x = float(start_point.x) + ratio * dx
        projected_y = float(start_point.y) + ratio * dy
        projected_distance = math.hypot(point_x - projected_x, point_y - projected_y)
        projected_measure = accumulated_length + ratio * segment_length

        if best_distance is None or projected_distance < best_distance:
            best_distance = projected_distance
            best_measure = projected_measure

        accumulated_length += segment_length

    if best_distance is None:
        return None
    return best_distance, best_measure


def _read_point_dataset(GIStools, points):
    reader = getattr(GIStools.DataManagement, "read_point_dataset_any", None)
    if reader is not None:
        return reader(points)
    return GIStools.DataManagement.read_point_dataset(points)


def _resolve_output_field_names(point_field_names, points_rid_field, routes_rid_field):
    rename_notes = []
    point_field_names = list(point_field_names)
    rid_field_name, add_rid_field = _resolve_rid_output_field_name(
        point_field_names,
        points_rid_field,
        routes_rid_field,
    )
    if add_rid_field and not _field_names_equal(rid_field_name, routes_rid_field):
        rename_notes.append(
            "Writing route IDs to '{}' because '{}' already exists in the input points.".format(
                rid_field_name,
                routes_rid_field,
            )
        )
    elif not add_rid_field and _field_names_equal(rid_field_name, routes_rid_field) and not _field_names_equal(points_rid_field, routes_rid_field):
        rename_notes.append(
            "Using existing point field '{}' for route IDs because '{}' already exists in the input points.".format(
                rid_field_name,
                routes_rid_field,
            )
        )

    if add_rid_field and not _field_name_exists(point_field_names, rid_field_name):
        point_field_names.append(rid_field_name)

    meas_field_name = "MEAS"
    if _field_name_exists(point_field_names, meas_field_name):
        meas_field_name = _make_unique_field_name("MEAS_ROUTE", point_field_names)
        rename_notes.append(
            "Writing measures to '{}' because 'MEAS' already exists in the input points.".format(
                meas_field_name,
            )
        )

    return rid_field_name, add_rid_field, meas_field_name, rename_notes


def _resolve_rid_output_field_name(point_field_names, points_rid_field, routes_rid_field):
    existing_name = _get_existing_field_name(point_field_names, routes_rid_field)
    if existing_name is None:
        return routes_rid_field, True

    if _field_names_equal(points_rid_field, routes_rid_field):
        return existing_name, False

    if not _field_name_exists(point_field_names, "RID"):
        return "RID", True

    return _make_unique_field_name("RID_ROUTE", point_field_names), True


def _field_name_exists(field_names, target_name):
    return _get_existing_field_name(field_names, target_name) is not None


def _get_existing_field_name(field_names, target_name):
    for field_name in field_names:
        if _field_names_equal(field_name, target_name):
            return field_name
    return None


def _field_names_equal(left_name, right_name):
    return str(left_name).lower() == str(right_name).lower()


def _make_unique_field_name(base_name, existing_field_names):
    existing_names = {str(field_name).lower() for field_name in existing_field_names}
    suffix = 1
    candidate = base_name
    while str(candidate).lower() in existing_names:
        candidate = "{}_{}".format(base_name, suffix)
        suffix += 1
    return candidate


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
