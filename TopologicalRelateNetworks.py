from __future__ import annotations

import RiverNetworkTools


def topological_relate_networks(
    routes_A,
    links_A,
    RID_A,
    routes_B,
    links_B,
    RID_B,
    frompoints,
    final_selection='BEST_FIT',
    GIStools=None,
    messages=None,
):
    if GIStools is None:
        GIStools = _autodetect_gistools()

    d8_features = list(GIStools.DataManagement.load_line_features(routes_A, [RID_A, 'ORIG_FID']))
    d8_links = list(
        GIStools.DataManagement.load_table_rows(
            links_A,
            [RiverNetworkTools.RiverNetwork.LINKS_DOWN_FIELD, RiverNetworkTools.RiverNetwork.LINKS_UP_FIELD],
        )
    )
    ref_features = list(GIStools.DataManagement.load_line_features(routes_B, [RID_B]))
    ref_links = list(
        GIStools.DataManagement.load_table_rows(
            links_B,
            [RiverNetworkTools.RiverNetwork.LINKS_DOWN_FIELD, RiverNetworkTools.RiverNetwork.LINKS_UP_FIELD],
        )
    )
    frompoint_info = _read_point_dataset_any(GIStools, frompoints, [RID_B])
    frompoint_features = []
    for row in frompoint_info['records']:
        if row.get('X') is None or row.get('Y') is None:
            continue
        frompoint_features.append(
            RiverNetworkTools.PointFeature(
                {RID_B: row[RID_B], '_oid': row['_oid']},
                RiverNetworkTools.Coordinate(float(row['X']), float(row['Y'])),
            )
        )
    output_rows = RiverNetworkTools.check_net_fit_from_upstream(
        d8_features,
        d8_links,
        RID_A,
        ref_features,
        ref_links,
        RID_B,
        frompoint_features,
        final_selection=final_selection,
        orig_fid_field='ORIG_FID',
        frompoint_id_field='_oid',
        feedback=_MessagesFeedback(messages),
    )
    info_a = GIStools.DataManagement.read_table_dataset(routes_A, [RID_A])
    info_b = GIStools.DataManagement.read_table_dataset(routes_B, [RID_B])
    return output_rows, info_a, info_b


def execute_TopologicalRelateNetworks(
    routes_A,
    links_A,
    RID_A,
    routes_B,
    links_B,
    RID_B,
    frompoints,
    out_table,
    messages=None,
    GIStools=None,
    final_selection='BEST_FIT',
):
    if GIStools is None:
        GIStools = _autodetect_gistools()

    try:
        output_rows, info_a, info_b = topological_relate_networks(
            routes_A,
            links_A,
            RID_A,
            routes_B,
            links_B,
            RID_B,
            frompoints,
            final_selection=final_selection,
            GIStools=GIStools,
            messages=messages,
        )
        return GIStools.DataManagement.write_output_table(
            out_table,
            output_rows,
            _empty_input_info(),
            [
                {
                    'name': RID_A,
                    'field_definition': info_a['field_definitions'].get(RID_A),
                    'dtype': 'int',
                },
                {
                    'name': 'MATCH_ID',
                    'field_definition': info_b['field_definitions'].get(RID_B),
                    'dtype': 'int',
                },
                {'name': 'TYPO', 'dtype': 'float'},
                {'name': 'CLOSEST', 'dtype': 'int'},
                {'name': 'SCORE', 'dtype': 'float'},
            ],
        )
    except Exception as exc:
        if messages is None:
            raise
        _add_error(messages, str(exc))


def execute_CheckNetFitFromUpStream(
    routes_A,
    links_A,
    RID_A,
    routes_B,
    links_B,
    RID_B,
    frompoints,
    out_table,
    messages=None,
    final_selection='BEST_FIT',
    GIStools=None,
):
    return execute_TopologicalRelateNetworks(
        routes_A,
        links_A,
        RID_A,
        routes_B,
        links_B,
        RID_B,
        frompoints,
        out_table,
        messages=messages,
        GIStools=GIStools,
        final_selection=final_selection,
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
