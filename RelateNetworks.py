from __future__ import annotations

import RiverNetworkTools


def relate_networks(
    shapefile_a,
    rid_a,
    shapefile_b,
    rid_b,
    feedback=None,
    strict_count=True,
    GIStools=None,
    messages=None,
):
    if GIStools is None:
        GIStools = _autodetect_gistools()

    effective_feedback = feedback if feedback is not None else _MessagesFeedback(messages)
    features_a = list(GIStools.DataManagement.load_line_features(shapefile_a, [rid_a]))
    features_b = list(GIStools.DataManagement.load_line_features(shapefile_b, [rid_b]))
    output_rid_a, output_rid_b, rename_notes = _resolve_output_field_names(rid_a, rid_b)
    for note in rename_notes:
        _warn_feedback(messages, effective_feedback, note)
    internal_rid_b = rid_b
    if str(rid_a).lower() == str(rid_b).lower():
        internal_rid_b = output_rid_b
        features_b = [
            RiverNetworkTools.LineFeature(
                dict(feature.attributes, **{internal_rid_b: feature.attributes[rid_b]}),
                list(feature.vertices),
            )
            for feature in features_b
        ]
    tuple_rows = []
    for row in RiverNetworkTools.relate_networks(
        features_a,
        rid_a,
        features_b,
        internal_rid_b,
        strict_count=strict_count,
        feedback=effective_feedback,
    ):
        tuple_rows.append((row[rid_a], row[internal_rid_b], row['PART_COUNT']))
    return tuple_rows


def execute_RelateNetworks(
    shapefile_A,
    RID_A,
    shapefile_B,
    RID_B,
    out_table,
    messages=None,
    GIStools=None,
    strict_count=True,
):
    if GIStools is None:
        GIStools = _autodetect_gistools()

    try:
        output_rid_a, output_rid_b, rename_notes = _resolve_output_field_names(RID_A, RID_B)
        for note in rename_notes:
            _add_warning(messages, note)
        tuple_rows = relate_networks(
            shapefile_A,
            RID_A,
            shapefile_B,
            RID_B,
            strict_count=strict_count,
            GIStools=GIStools,
            messages=messages,
        )
        output_rows = [
            {output_rid_a: row[0], output_rid_b: row[1], 'PART_COUNT': row[2]}
            for row in tuple_rows
        ]
        info_a = GIStools.DataManagement.read_table_dataset(shapefile_A, [RID_A])
        info_b = GIStools.DataManagement.read_table_dataset(shapefile_B, [RID_B])
        return GIStools.DataManagement.write_output_table(
            out_table,
            output_rows,
            _empty_input_info(),
            [
                {
                    'name': output_rid_a,
                    'field_definition': info_a['field_definitions'].get(RID_A),
                    'dtype': 'int',
                },
                {
                    'name': output_rid_b,
                    'field_definition': info_b['field_definitions'].get(RID_B),
                    'dtype': 'int',
                },
                {'name': 'PART_COUNT', 'dtype': 'int'},
            ],
        )
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


def _resolve_output_field_names(rid_a, rid_b):
    if str(rid_a).lower() != str(rid_b).lower():
        return rid_a, rid_b, []
    renamed = f'{rid_b}_1'
    return rid_a, renamed, [f"Output field '{rid_b}' renamed to '{renamed}' to avoid collision."]


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


def _warn_feedback(messages, feedback, message):
    if messages is not None:
        messages.add_warning(message)
        return
    if feedback is not None and hasattr(feedback, 'pushWarning'):
        feedback.pushWarning(message)


def _add_error(messages, message):
    if messages is not None:
        messages.add_error(message)
    raise RuntimeError(message)
