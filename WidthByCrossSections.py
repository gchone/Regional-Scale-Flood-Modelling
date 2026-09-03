from __future__ import annotations


def execute_WidthByCrossSections(
    streamnetwork,
    idfield,
    riverbed,
    ineffarea,
    maxwidth,
    spacing,
    transects,
    cspoints,
    GIStools=None,
    messages=None,
):
    if GIStools is None:
        GIStools = _autodetect_gistools()

    if idfield in [None, ""]:
        _add_error(messages, "A route ID field name must be provided.")

    maxwidth_value = _as_float(maxwidth)
    if maxwidth_value is None or maxwidth_value <= 0.0:
        _add_error(messages, "Maximum width of cross-sections must be greater than 0.")

    spacing_value = _as_float(spacing)
    if spacing_value is None or spacing_value <= 0.0:
        _add_error(messages, "Interval between cross-sections must be greater than 0.")

    if transects in [None, ""]:
        _add_error(messages, "An output path for cross-sections must be provided.")
    if cspoints in [None, ""]:
        _add_error(messages, "An output path for cross-section points must be provided.")
    if str(transects) == str(cspoints):
        _add_error(messages, "Cross-sections and cross-section points outputs must be different datasets.")

    streamnetwork_dataset = _open_vector_dataset(GIStools, streamnetwork)
    riverbed_dataset = _open_vector_dataset(GIStools, riverbed)
    ineffarea_dataset = None if ineffarea in [None, "", "#"] else _open_vector_dataset(GIStools, ineffarea)

    _add_message(messages, "Computing river widths from cross-sections...")
    return GIStools.Geoprocessing.compute_width_by_cross_sections(
        streamnetwork_dataset,
        idfield,
        riverbed_dataset,
        ineffarea_dataset,
        maxwidth_value,
        spacing_value,
        transects,
        cspoints,
        messages=messages,
    )


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


def _open_vector_dataset(GIStools, dataset, layer_name=None):
    opener = getattr(GIStools.DataManagement, "open_vector_dataset", None)
    if opener is None:
        return dataset
    return opener(dataset, layer_name)


def _as_float(value):
    if value in [None, ""]:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _add_message(messages, message):
    if messages is not None:
        messages.add_message(message)


def _add_error(messages, message):
    if messages is not None:
        messages.add_error(message)
    raise RuntimeError(message)
