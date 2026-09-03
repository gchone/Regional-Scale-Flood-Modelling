from __future__ import annotations

import RiverNetworkTools


def create_network_from_fc(
    rivernet,
    rid_field,
    downstream_field,
    channeltype_field=None,
    GIStools=None,
    messages=None,
    coord_round_digits=1,
):
    if GIStools is None:
        GIStools = _autodetect_gistools()

    field_names = _unique_field_names([rid_field, downstream_field, channeltype_field])
    route_info = GIStools.DataManagement.read_table_dataset(rivernet)
    route_features = list(GIStools.DataManagement.load_line_features(rivernet))
    if len(route_features) == 0:
        _add_error(messages, 'No valid line features found.')

    output_features, link_rows = RiverNetworkTools.create_network_from_fc(
        route_features,
        rid_field,
        downstream_field,
        channeltype_field=channeltype_field,
        feedback=_MessagesFeedback(messages),
        coord_round_digits=coord_round_digits,
    )
    return output_features, link_rows, route_info, GIStools.DataManagement.get_spatial_reference(rivernet)


def execute_CreateNetworkFromFC(
    rivernet,
    route_shapefile,
    routelinks_table,
    routeID_field,
    downstream_reach_field,
    channeltype_field=None,
    GIStools=None,
    messages=None,
):
    if GIStools is None:
        GIStools = _autodetect_gistools()

    try:
        output_features, link_rows, route_info, spatial_reference = create_network_from_fc(
            rivernet,
            routeID_field,
            downstream_reach_field,
            channeltype_field=channeltype_field,
            GIStools=GIStools,
            messages=messages,
        )
        GIStools.DataManagement.write_line_features(
            route_shapefile,
            output_features,
            route_info,
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
        _add_message(messages, f'Created {len(output_features)} route(s) and {len(link_rows)} link(s).')
        return route_shapefile
    except Exception as exc:
        if messages is None:
            raise
        _add_error(messages, str(exc))


def execute_CreateTreeFromShapefile(
    rivernet,
    route_shapefile,
    routelinks_table,
    routeID_field,
    downstream_reach_field,
    messages,
    channeltype_field=None,
    GIStools=None,
):
    return execute_CreateNetworkFromFC(
        rivernet,
        route_shapefile,
        routelinks_table,
        routeID_field,
        downstream_reach_field,
        channeltype_field=channeltype_field,
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


def _unique_field_names(field_names):
    result = []
    seen = set()
    for field_name in field_names:
        if field_name in [None, '']:
            continue
        key = str(field_name).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(field_name)
    return result


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
