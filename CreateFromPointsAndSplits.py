from __future__ import annotations

import RiverNetworkTools


def create_from_points_and_splits(
    network_shp,
    links_table,
    RID_field,
    links_up_field='UpID',
    links_down_field='DownID',
    GIStools=None,
    messages=None,
):
    if GIStools is None:
        GIStools = _autodetect_gistools()

    route_features = list(GIStools.DataManagement.load_line_features(network_shp, [RID_field]))
    link_rows = list(GIStools.DataManagement.load_table_rows(links_table, [links_down_field, links_up_field]))
    return RiverNetworkTools.create_from_points_and_splits(
        route_features,
        link_rows,
        RID_field,
        links_up_field=links_up_field,
        links_down_field=links_down_field,
        feedback=_MessagesFeedback(messages),
    )


def execute_CreateFromPointsAndSplits(
    network_shp,
    links_table,
    RID_field,
    points,
    splits,
    GIStools=None,
    messages=None,
):
    if GIStools is None:
        GIStools = _autodetect_gistools()

    try:
        from_points, split_points = create_from_points_and_splits(
            network_shp,
            links_table,
            RID_field,
            GIStools=GIStools,
            messages=messages,
        )
        route_info = GIStools.DataManagement.read_table_dataset(network_shp, [RID_field])
        spatial_reference = GIStools.DataManagement.get_spatial_reference(network_shp)
        GIStools.DataManagement.write_point_features(
            points,
            from_points,
            {
                'field_names': [RID_field],
                'field_definitions': route_info['field_definitions'],
            },
            spatial_reference=spatial_reference,
        )
        GIStools.DataManagement.write_point_features(
            splits,
            split_points,
            _empty_input_info(),
            spatial_reference=spatial_reference,
        )
        _add_message(messages, f'Created {len(from_points)} from-point(s) and {len(split_points)} split-point(s).')
        return points, splits
    except Exception as exc:
        if messages is None:
            raise
        _add_error(messages, str(exc))


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
