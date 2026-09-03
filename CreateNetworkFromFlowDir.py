from __future__ import annotations

import RiverNetworkTools


def create_network_from_flowdir(
    r_flowdir,
    str_frompoints,
    routeID_field,
    split_pts=None,
    tolerance=None,
    GIStools=None,
    messages=None,
):
    if GIStools is None:
        GIStools = _autodetect_gistools()

    frompoints_info = _read_point_dataset_any(GIStools, str_frompoints, [routeID_field])
    fp_features = []
    for row in frompoints_info['records']:
        if row.get('X') in [None, ''] or row.get('Y') in [None, '']:
            continue
        fp_features.append(
            RiverNetworkTools.PointFeature(
                {routeID_field: row[routeID_field], '_oid': row['_oid']},
                RiverNetworkTools.Coordinate(float(row['X']), float(row['Y'])),
            )
        )

    split_features = []
    if split_pts not in [None, '']:
        split_info = _read_point_dataset_any(GIStools, split_pts)
        for row in split_info['records']:
            if row.get('X') in [None, ''] or row.get('Y') in [None, '']:
                continue
            split_features.append(
                RiverNetworkTools.PointFeature(
                    {},
                    RiverNetworkTools.Coordinate(float(row['X']), float(row['Y'])),
                )
            )

    flowdir = GIStools.RasterAccess.FlowDirectionRaster(r_flowdir)
    tolerance_value = 10000.0 if tolerance in [None, ''] else float(tolerance)
    route_features, link_rows, point_rows = RiverNetworkTools.tree_from_flowdir(
        flowdir,
        fp_features,
        split_features,
        routeID_field,
        tolerance=tolerance_value,
        feedback=_MessagesFeedback(messages),
        from_point_id_field='_oid',
    )

    point_features = [
        RiverNetworkTools.PointFeature(
            {
                'id': int(point.id),
                'RID': int(point.rid),
                'dist': float(point.dist),
                'offset': float(point.offset),
                'X': float(point.x),
                'Y': float(point.y),
                'row': int(point.row),
                'col': int(point.col),
            },
            RiverNetworkTools.Coordinate(float(point.x), float(point.y)),
        )
        for point in point_rows
    ]
    return route_features, link_rows, point_features, frompoints_info, GIStools.DataManagement.get_spatial_reference(str_frompoints)


def execute_CreateNetworkFromFlowDir(
    r_flowdir,
    str_frompoints,
    route_shapefile,
    routelinks_table,
    routeID_field,
    str_output_points,
    split_pts=None,
    tolerance=None,
    GIStools=None,
    messages=None,
):
    if GIStools is None:
        GIStools = _autodetect_gistools()

    try:
        route_features, link_rows, point_features, frompoints_info, spatial_reference = create_network_from_flowdir(
            r_flowdir,
            str_frompoints,
            routeID_field,
            split_pts=split_pts,
            tolerance=tolerance,
            GIStools=GIStools,
            messages=messages,
        )
        GIStools.DataManagement.write_line_features(
            route_shapefile,
            route_features,
            {
                'field_names': [routeID_field],
                'field_definitions': frompoints_info['field_definitions'],
            },
            extra_fields=[{'name': 'ORIG_FID', 'dtype': 'int'}],
            spatial_reference=spatial_reference,
            has_m=True,
        )
        GIStools.DataManagement.write_output_table(
            routelinks_table,
            [
                {
                    RiverNetworkTools.RiverNetwork.LINKS_DOWN_FIELD: int(link.downstream_id),
                    RiverNetworkTools.RiverNetwork.LINKS_UP_FIELD: int(link.upstream_id),
                }
                for link in link_rows
            ],
            _empty_input_info(),
            [
                {'name': RiverNetworkTools.RiverNetwork.LINKS_DOWN_FIELD, 'dtype': 'int'},
                {'name': RiverNetworkTools.RiverNetwork.LINKS_UP_FIELD, 'dtype': 'int'},
            ],
        )
        GIStools.DataManagement.write_point_features(
            str_output_points,
            point_features,
            _empty_input_info(),
            extra_fields=[
                {'name': 'id', 'dtype': 'int'},
                {'name': 'RID', 'dtype': 'int'},
                {'name': 'dist', 'dtype': 'float'},
                {'name': 'offset', 'dtype': 'float'},
                {'name': 'X', 'dtype': 'float'},
                {'name': 'Y', 'dtype': 'float'},
                {'name': 'row', 'dtype': 'int'},
                {'name': 'col', 'dtype': 'int'},
            ],
            spatial_reference=spatial_reference,
        )
        _add_message(messages, f'Created {len(route_features)} route(s), {len(link_rows)} link(s), and {len(point_features)} path point(s).')
        return route_shapefile
    except Exception as exc:
        if messages is None:
            raise
        _add_error(messages, str(exc))


def execute_TreeFromFlowDir(
    r_flowdir,
    str_frompoints,
    route_shapefile,
    routelinks_table,
    routeID_field,
    str_output_points,
    messages,
    split_pts=None,
    tolerance=None,
    GIStools=None,
):
    return execute_CreateNetworkFromFlowDir(
        r_flowdir,
        str_frompoints,
        route_shapefile,
        routelinks_table,
        routeID_field,
        str_output_points,
        split_pts=split_pts,
        tolerance=tolerance,
        GIStools=GIStools,
        messages=messages,
    )


class _MessagesFeedback:
    def __init__(self, messages):
        self.messages = messages

    def pushInfo(self, message):
        _add_message(self.messages, message)

    def pushWarning(self, message):
        _add_warning(self.messages, message)

    def isCanceled(self):
        return False

    def setProgress(self, progress):
        return


def _read_point_dataset_any(GIStools, dataset, field_names=None):
    reader = getattr(GIStools.DataManagement, 'read_point_dataset_any', None)
    if reader is not None:
        return reader(dataset, field_names)
    return GIStools.DataManagement.read_point_dataset(dataset, field_names)


def _empty_input_info():
    return {'records': [], 'field_names': [], 'field_definitions': {}}


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
