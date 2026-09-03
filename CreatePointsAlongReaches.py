from __future__ import annotations

import RiverNetworkTools


def create_points_along_reaches(
    network_shp,
    links_table,
    RID_field,
    interval,
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
    route_info = GIStools.DataManagement.read_table_dataset(network_shp, [RID_field])
    output_rows = RiverNetworkTools.place_points_at_regular_interval(
        route_features,
        link_rows,
        RID_field,
        float(interval),
        feedback=_MessagesFeedback(messages),
    )
    return output_rows, route_info


def execute_CreatePointsAlongReaches(
    network_shp,
    links_table,
    RID_field,
    interval,
    output_pt,
    GIStools=None,
    messages=None,
):
    if GIStools is None:
        GIStools = _autodetect_gistools()

    try:
        output_rows, route_info = create_points_along_reaches(
            network_shp,
            links_table,
            RID_field,
            interval,
            GIStools=GIStools,
            messages=messages,
        )
        return GIStools.DataManagement.write_output_table(
            output_pt,
            output_rows,
            _empty_input_info(),
            [
                {'name': 'id', 'dtype': 'int'},
                {
                    'name': 'RID',
                    'field_definition': route_info['field_definitions'].get(RID_field),
                    'dtype': 'int',
                },
                {'name': 'MEAS', 'dtype': 'float'},
            ],
        )
    except Exception as exc:
        if messages is None:
            raise
        _add_error(messages, str(exc))


def execute_PlacePointsAlongReaches(
    network_shp,
    links_table,
    RID_field,
    interval,
    output_pt,
    GIStools=None,
    messages=None,
):
    return execute_CreatePointsAlongReaches(
        network_shp,
        links_table,
        RID_field,
        interval,
        output_pt,
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
