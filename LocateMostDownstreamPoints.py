from __future__ import annotations

import RiverNetworkTools


def locate_most_downstream_points(
    network_shp,
    links_table,
    RID_field,
    datapoints,
    id_field_pts,
    RID_field_pts,
    Distance_field_pts,
    X_field_pts,
    Y_field_pts,
    GIStools=None,
    messages=None,
):
    if GIStools is None:
        GIStools = _autodetect_gistools()

    route_features = list(GIStools.DataManagement.load_line_features(network_shp, [RID_field]))
    link_rows = list(
        GIStools.DataManagement.load_table_rows(
            links_table,
            [RiverNetworkTools.RiverNetwork.LINKS_DOWN_FIELD, RiverNetworkTools.RiverNetwork.LINKS_UP_FIELD],
        )
    )
    datapoint_rows = GIStools.DataManagement.read_table_dataset(
        datapoints,
        [id_field_pts, RID_field_pts, Distance_field_pts, X_field_pts, Y_field_pts],
    )
    return RiverNetworkTools.locate_most_downstream_points(
        route_features,
        link_rows,
        RID_field,
        datapoint_rows['records'],
        id_field_pts,
        RID_field_pts,
        Distance_field_pts,
        X_field_pts,
        Y_field_pts,
    )


def execute_LocateMostDownstreamPoints(
    network_shp,
    links_table,
    RID_field,
    datapoints,
    id_field_pts,
    RID_field_pts,
    Distance_field_pts,
    X_field_pts,
    Y_field_pts,
    output_pts,
    GIStools=None,
    messages=None,
):
    if GIStools is None:
        GIStools = _autodetect_gistools()

    try:
        output_features = locate_most_downstream_points(
            network_shp,
            links_table,
            RID_field,
            datapoints,
            id_field_pts,
            RID_field_pts,
            Distance_field_pts,
            X_field_pts,
            Y_field_pts,
            GIStools=GIStools,
            messages=messages,
        )
        datapoints_info = GIStools.DataManagement.read_table_dataset(datapoints, [id_field_pts])
        spatial_reference = GIStools.DataManagement.get_spatial_reference(network_shp)
        GIStools.DataManagement.write_point_features(
            output_pts,
            output_features,
            {
                'field_names': [id_field_pts],
                'field_definitions': datapoints_info['field_definitions'],
            },
            spatial_reference=spatial_reference,
        )
        _add_message(messages, f'Created {len(output_features)} downstream point(s).')
        return output_pts
    except Exception as exc:
        if messages is None:
            raise
        _add_error(messages, str(exc))


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


def _add_error(messages, message):
    if messages is not None:
        messages.add_error(message)
    raise RuntimeError(message)
