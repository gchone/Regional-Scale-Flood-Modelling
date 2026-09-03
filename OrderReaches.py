from __future__ import annotations

import math

import RiverNetworkTools
from LocateMostDownstreamPoints import locate_most_downstream_points
from LocatePointsAlongRoutes import locate_points_along_route_rows


def order_reaches(
    routes,
    links,
    RID_field,
    r_flowacc,
    routeD8,
    linksD8,
    ptsonD8,
    relatetable,
    outputfield,
    GIStools=None,
    messages=None,
):
    if GIStools is None:
        GIStools = _autodetect_gistools()

    route_info = GIStools.DataManagement.read_table_dataset(routes)
    route_features = list(GIStools.DataManagement.load_line_features(routes))
    links_rows = list(
        GIStools.DataManagement.load_table_rows(
            links,
            [RiverNetworkTools.RiverNetwork.LINKS_DOWN_FIELD, RiverNetworkTools.RiverNetwork.LINKS_UP_FIELD],
        )
    )

    downstream_points = locate_most_downstream_points(
        routeD8,
        linksD8,
        RID_field,
        ptsonD8,
        'id',
        'RID',
        'dist',
        'X',
        'Y',
        GIStools=GIStools,
        messages=messages,
    )

    pathpoint_info = GIStools.DataManagement.read_table_dataset(ptsonD8, ['id', 'RID', 'dist', 'X', 'Y'])
    pathpoints_by_id = {int(row['id']): row for row in pathpoint_info['records'] if row.get('id') is not None}

    relate_info = GIStools.DataManagement.read_table_dataset(relatetable)
    relate_main_field, relate_d8_field = _resolve_relate_fields(relate_info['field_names'], RID_field)
    d8_to_main = {}
    for row in relate_info['records']:
        main_value = row.get(relate_main_field)
        d8_value = row.get(relate_d8_field)
        if main_value is None or d8_value is None:
            continue
        d8_to_main[int(d8_value)] = main_value

    raster_grid = GIStools.RasterAccess.read_raster_grid(r_flowacc)
    qpoints_main_rows = []
    for feature in downstream_points:
        point_id = feature.attributes.get('id')
        if point_id is None:
            continue
        point_row = pathpoints_by_id.get(int(point_id))
        if point_row is None:
            _add_error(messages, f'Point id {point_id} was not found in the D8 path points table.')
        flowacc = _sample_raster_grid(raster_grid, point_row.get('X'), point_row.get('Y'))
        if flowacc is None:
            _add_warning(messages, f'Point id {point_id} falls outside the flow-accumulation raster and was skipped.')
            continue
        d8_rid = point_row.get('RID')
        if d8_rid is None:
            continue
        main_rid = d8_to_main.get(int(d8_rid))
        if main_rid is None:
            _add_warning(messages, f'D8 reach {d8_rid} has no relate-table match and was skipped.')
            continue
        qpoints_main_rows.append(
            {
                'id': int(point_id),
                RID_field: main_rid,
                'flowacc': float(flowacc),
                'X': float(point_row['X']),
                'Y': float(point_row['Y']),
            }
        )

    located_rows = locate_points_along_route_rows(
        qpoints_main_rows,
        RID_field,
        route_features,
        RID_field,
        10000.0,
        RID_field,
        'MEAS',
    )
    output_features = RiverNetworkTools.order_tree_by_flow_acc(
        route_features,
        links_rows,
        RID_field,
        located_rows,
        'id',
        RID_field,
        'MEAS',
        'flowacc',
        output_field=outputfield,
    )
    return output_features, route_info, GIStools.DataManagement.get_spatial_reference(routes)


def execute_OrderReaches(
    routes,
    links,
    RID_field,
    r_flowacc,
    routeD8,
    linksD8,
    ptsonD8,
    relatetable,
    outputfield,
    messages=None,
    GIStools=None,
    output_routes=None,
):
    if GIStools is None:
        GIStools = _autodetect_gistools()

    try:
        output_features, route_info, spatial_reference = order_reaches(
            routes,
            links,
            RID_field,
            r_flowacc,
            routeD8,
            linksD8,
            ptsonD8,
            relatetable,
            outputfield,
            GIStools=GIStools,
            messages=messages,
        )
        if output_routes not in [None, '']:
            return GIStools.DataManagement.write_line_features(
                output_routes,
                output_features,
                route_info,
                extra_fields=[{'name': outputfield, 'dtype': 'int'}],
                spatial_reference=spatial_reference,
                has_m=_has_any_m(output_features),
            )
        updater = getattr(GIStools.DataManagement, 'update_line_attributes', None)
        if updater is None:
            return output_features
        updater(
            routes,
            output_features,
            RID_field,
            [outputfield],
            extra_fields=[{'name': outputfield, 'dtype': 'int'}],
        )
        return routes
    except Exception as exc:
        if messages is None:
            raise
        _add_error(messages, str(exc))


def _resolve_relate_fields(field_names, rid_field):
    candidate_fields = [field_name for field_name in field_names if str(field_name).lower() != 'part_count']
    if len(candidate_fields) < 2:
        raise ValueError('Relate table must contain two route ID fields and PART_COUNT.')
    main_field = None
    for field_name in candidate_fields:
        if str(field_name).lower() == str(rid_field).lower():
            main_field = field_name
            break
    if main_field is None:
        main_field = candidate_fields[0]
    d8_field = candidate_fields[1] if candidate_fields[0] == main_field else candidate_fields[0]
    return main_field, d8_field


def _sample_raster_grid(raster_grid, x_value, y_value):
    if x_value in [None, ''] or y_value in [None, '']:
        return None
    col = int((float(x_value) - float(raster_grid['x_min'])) / float(raster_grid['pixel_width']))
    row = int((float(raster_grid['y_max']) - float(y_value)) / float(raster_grid['pixel_height']))
    if row < 0 or col < 0 or row >= int(raster_grid['height']) or col >= int(raster_grid['width']):
        return None
    value = raster_grid['array'][row][col]
    nodata = raster_grid.get('nodata')
    if nodata is not None:
        try:
            if math.isnan(nodata):
                if math.isnan(value):
                    return None
            elif float(value) == float(nodata):
                return None
        except Exception:
            pass
    try:
        if math.isnan(value):
            return None
    except Exception:
        pass
    return float(value)


def _has_any_m(features):
    for feature in features:
        for vertex in feature.vertices:
            if getattr(vertex, 'm', None) is not None:
                return True
    return False


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
    raise ValueError('A GIStools package must be provided.')


def _add_warning(messages, message):
    if messages is not None:
        messages.add_warning(message)


def _add_error(messages, message):
    if messages is not None:
        messages.add_error(message)
    raise RuntimeError(message)
