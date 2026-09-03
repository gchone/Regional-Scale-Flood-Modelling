from __future__ import annotations

import RiverNetworkTools


def flow_direction_network(
    routes,
    links,
    RID_field,
    r_flow_dir,
    GIStools=None,
    messages=None,
):
    if GIStools is None:
        GIStools = _autodetect_gistools()

    route_features = list(GIStools.DataManagement.load_line_features(routes, [RID_field]))
    link_rows = list(
        GIStools.DataManagement.load_table_rows(
            links,
            [RiverNetworkTools.RiverNetwork.LINKS_DOWN_FIELD, RiverNetworkTools.RiverNetwork.LINKS_UP_FIELD],
        )
    )
    route_info = GIStools.DataManagement.read_table_dataset(routes, [RID_field])

    _add_message(messages, 'Step 1/3: Building from-points and split-points...')
    from_points, split_points = RiverNetworkTools.create_from_points_and_splits(
        route_features,
        link_rows,
        RID_field,
        feedback=_MessagesFeedback(messages),
    )
    trace_points = []
    for index, point in enumerate(from_points, start=1):
        trace_points.append(
            RiverNetworkTools.PointFeature(
                {RID_field: point.attributes[RID_field], '_oid': index},
                point.point,
            )
        )

    _add_message(messages, 'Step 2/3: Tracing D8 flow paths...')
    flowdir = GIStools.RasterAccess.FlowDirectionRaster(r_flow_dir)
    routed8_features, linksd8_rows, ptsond8_rows = RiverNetworkTools.tree_from_flowdir(
        flowdir,
        trace_points,
        split_points,
        RID_field,
        tolerance=10000.0,
        feedback=_MessagesFeedback(messages),
        from_point_id_field='_oid',
    )

    _add_message(messages, 'Step 3/3: Relating original network to D8 network...')
    relate_rows, output_rid_a, output_rid_b = _relate_route_features(
        route_features,
        RID_field,
        routed8_features,
        RID_field,
        messages,
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
        for point in ptsond8_rows
    ]

    return (
        routed8_features,
        linksd8_rows,
        point_features,
        relate_rows,
        output_rid_a,
        output_rid_b,
        route_info,
        GIStools.DataManagement.get_spatial_reference(routes),
    )


def execute_FlowDirectionNetwork(
    routes,
    links,
    RID_field,
    r_flow_dir,
    routeD8,
    linksD8,
    ptsonD8,
    relatetable,
    messages=None,
    GIStools=None,
):
    if GIStools is None:
        GIStools = _autodetect_gistools()

    try:
        routed8_features, linksd8_rows, point_features, relate_rows, output_rid_a, output_rid_b, route_info, spatial_reference = flow_direction_network(
            routes,
            links,
            RID_field,
            r_flow_dir,
            GIStools=GIStools,
            messages=messages,
        )
        GIStools.DataManagement.write_line_features(
            routeD8,
            routed8_features,
            {
                'field_names': [RID_field],
                'field_definitions': route_info['field_definitions'],
            },
            extra_fields=[{'name': 'ORIG_FID', 'dtype': 'int'}],
            spatial_reference=spatial_reference,
            has_m=True,
        )
        GIStools.DataManagement.write_output_table(
            linksD8,
            [
                {
                    RiverNetworkTools.RiverNetwork.LINKS_DOWN_FIELD: int(link.downstream_id),
                    RiverNetworkTools.RiverNetwork.LINKS_UP_FIELD: int(link.upstream_id),
                }
                for link in linksd8_rows
            ],
            _empty_input_info(),
            [
                {'name': RiverNetworkTools.RiverNetwork.LINKS_DOWN_FIELD, 'dtype': 'int'},
                {'name': RiverNetworkTools.RiverNetwork.LINKS_UP_FIELD, 'dtype': 'int'},
            ],
        )
        GIStools.DataManagement.write_point_features(
            ptsonD8,
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
        GIStools.DataManagement.write_output_table(
            relatetable,
            relate_rows,
            _empty_input_info(),
            [
                {
                    'name': output_rid_a,
                    'field_definition': route_info['field_definitions'].get(RID_field),
                    'dtype': 'int',
                },
                {
                    'name': output_rid_b,
                    'field_definition': route_info['field_definitions'].get(RID_field),
                    'dtype': 'int',
                },
                {'name': 'PART_COUNT', 'dtype': 'int'},
            ],
        )
        return routeD8, linksD8, ptsonD8, relatetable
    except Exception as exc:
        if messages is None:
            raise
        _add_error(messages, str(exc))


def execute_FlowDirNetwork(
    routes,
    links,
    RID_field,
    r_flow_dir,
    routeD8,
    linksD8,
    ptsonD8,
    relatetable,
    messages=None,
    GIStools=None,
):
    return execute_FlowDirectionNetwork(
        routes,
        links,
        RID_field,
        r_flow_dir,
        routeD8,
        linksD8,
        ptsonD8,
        relatetable,
        messages=messages,
        GIStools=GIStools,
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


def _relate_route_features(route_features_a, rid_a, route_features_b, rid_b, messages):
    internal_rid_b = rid_b
    relate_features_b = route_features_b
    if str(rid_a).lower() == str(rid_b).lower():
        internal_rid_b = f'{rid_b}_1'
        relate_features_b = [
            RiverNetworkTools.LineFeature(dict(feature.attributes, **{internal_rid_b: feature.attributes[rid_b]}), list(feature.vertices))
            for feature in route_features_b
        ]
    raw_rows = RiverNetworkTools.relate_networks(
        route_features_a,
        rid_a,
        relate_features_b,
        internal_rid_b,
        strict_count=True,
        feedback=_MessagesFeedback(messages),
    )
    output_rid_a = rid_a
    output_rid_b = rid_b if str(rid_a).lower() != str(rid_b).lower() else f'{rid_b}_1'
    if output_rid_b != rid_b:
        _add_warning(messages, f"Output field '{rid_b}' renamed to '{output_rid_b}' to avoid collision.")
    output_rows = []
    for row in raw_rows:
        output_rows.append(
            {
                output_rid_a: row[rid_a],
                output_rid_b: row[internal_rid_b],
                'PART_COUNT': row['PART_COUNT'],
            }
        )
    return output_rows, output_rid_a, output_rid_b


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
