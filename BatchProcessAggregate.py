from __future__ import annotations

import math
import os

import numpy as np


VALID_AGGREGATIONS = {"SUM", "MAXIMUM", "MEAN", "MEDIAN", "MINIMUM"}
VALID_EXTENT_HANDLING = {"EXPAND", "TRUNCATE"}
VALID_NODATA_HANDLING = {"DATA", "NODATA"}
EPSILON = 1e-9


def execute_BatchProcessAggregate(
    dem_list,
    cell_factor,
    aggregation_type,
    extent_handling,
    ignore_nodata,
    output_dir,
    GIStools=None,
    messages=None,
):
    if GIStools is None:
        GIStools = _autodetect_gistools()

    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)

    factor = int(cell_factor)
    aggregation = str(aggregation_type).upper()
    extent_mode = str(extent_handling).upper()
    nodata_mode = str(ignore_nodata).upper()

    if factor < 1:
        _add_error(messages, "Cell factor must be a positive integer.")
    if aggregation not in VALID_AGGREGATIONS:
        _add_error(messages, f"Unsupported aggregation type: {aggregation_type}")
    if extent_mode not in VALID_EXTENT_HANDLING:
        _add_error(messages, f"Unsupported extent handling mode: {extent_handling}")
    if nodata_mode not in VALID_NODATA_HANDLING:
        _add_error(messages, f"Unsupported NoData handling mode: {ignore_nodata}")

    outputs = []
    snap_info = None

    for raster in dem_list:
        raster_label = _get_raster_label(raster)
        _add_message(messages, f"Processing {raster_label}")

        raster_data = GIStools.RasterAccess.read_raster_grid(raster)
        subset, output_grid = _build_aligned_subset(raster_data, factor, extent_mode, snap_info)
        aggregated = _aggregate_blocks(subset, factor, aggregation, nodata_mode)
        if aggregated.size == 0:
            _add_error(messages, f"Aggregation produced no output cells for {raster_label}")

        output_reference = dict(raster_data)
        output_reference.update(output_grid)
        output_reference["array"] = aggregated
        output_reference["width"] = int(output_grid["width"])
        output_reference["height"] = int(output_grid["height"])

        output_path = os.path.join(output_dir, _get_raster_basename(raster))
        nodata_value = _resolve_output_nodata(raster_data.get("nodata"))
        saved_path = GIStools.RasterAccess.write_raster_grid(
            output_reference,
            _replace_nan(aggregated, nodata_value),
            output_path,
            nodata=nodata_value,
        )
        outputs.append(saved_path)

        if snap_info is None:
            snap_info = {
                "x_min": float(output_grid["x_min"]),
                "y_max": float(output_grid["y_max"]),
                "pixel_width": float(output_grid["pixel_width"]),
                "pixel_height": float(output_grid["pixel_height"]),
            }

    return outputs


def _build_aligned_subset(raster_data, factor, extent_mode, snap_info):
    src_array = np.asarray(raster_data["array"], dtype=float)
    src_rows, src_cols = src_array.shape
    src_x_min = float(raster_data["x_min"])
    src_y_max = float(raster_data["y_max"])
    src_y_min = float(raster_data["y_min"])
    src_pixel_width = float(raster_data["pixel_width"])
    src_pixel_height = float(raster_data["pixel_height"])
    target_pixel_width = src_pixel_width * factor
    target_pixel_height = src_pixel_height * factor

    if snap_info is None:
        snap_x_min = src_x_min
        snap_y_max = src_y_max
    else:
        snap_x_min = float(snap_info["x_min"])
        snap_y_max = float(snap_info["y_max"])

    src_x_max = src_x_min + src_cols * src_pixel_width

    if extent_mode == "EXPAND":
        left_index = math.floor(((src_x_min - snap_x_min) / target_pixel_width) + EPSILON)
        right_index = math.ceil(((src_x_max - snap_x_min) / target_pixel_width) - EPSILON)
        top_index = math.floor(((snap_y_max - src_y_max) / target_pixel_height) + EPSILON)
        bottom_index = math.ceil(((snap_y_max - src_y_min) / target_pixel_height) - EPSILON)
    else:
        left_index = math.ceil(((src_x_min - snap_x_min) / target_pixel_width) - EPSILON)
        right_index = math.floor(((src_x_max - snap_x_min) / target_pixel_width) + EPSILON)
        top_index = math.ceil(((snap_y_max - src_y_max) / target_pixel_height) - EPSILON)
        bottom_index = math.floor(((snap_y_max - src_y_min) / target_pixel_height) + EPSILON)

    out_cols = max(0, int(right_index - left_index))
    out_rows = max(0, int(bottom_index - top_index))
    if out_cols == 0 or out_rows == 0:
        return np.empty((0, 0), dtype=float), {
            "x_min": snap_x_min + left_index * target_pixel_width,
            "y_max": snap_y_max - top_index * target_pixel_height,
            "y_min": snap_y_max - bottom_index * target_pixel_height,
            "pixel_width": target_pixel_width,
            "pixel_height": target_pixel_height,
            "width": out_cols,
            "height": out_rows,
        }

    subset_cols = out_cols * factor
    subset_rows = out_rows * factor
    subset = np.full((subset_rows, subset_cols), np.nan, dtype=float)
    valid_source = src_array.copy()
    valid_source[~_valid_data_mask(valid_source, raster_data.get("nodata"))] = np.nan

    output_x_min = snap_x_min + left_index * target_pixel_width
    output_y_max = snap_y_max - top_index * target_pixel_height

    source_col_start = max(0, _cell_offset(output_x_min - src_x_min, src_pixel_width))
    source_row_start = max(0, _cell_offset(src_y_max - output_y_max, src_pixel_height))
    subset_col_start = max(0, _cell_offset(src_x_min - output_x_min, src_pixel_width))
    subset_row_start = max(0, _cell_offset(output_y_max - src_y_max, src_pixel_height))

    copy_cols = min(src_cols - source_col_start, subset_cols - subset_col_start)
    copy_rows = min(src_rows - source_row_start, subset_rows - subset_row_start)
    if copy_cols > 0 and copy_rows > 0:
        subset[
            subset_row_start:subset_row_start + copy_rows,
            subset_col_start:subset_col_start + copy_cols,
        ] = valid_source[
            source_row_start:source_row_start + copy_rows,
            source_col_start:source_col_start + copy_cols,
        ]

    return subset, {
        "x_min": output_x_min,
        "y_max": output_y_max,
        "y_min": output_y_max - out_rows * target_pixel_height,
        "pixel_width": target_pixel_width,
        "pixel_height": target_pixel_height,
        "width": out_cols,
        "height": out_rows,
    }


def _aggregate_blocks(subset, factor, aggregation, nodata_mode):
    if subset.size == 0:
        return np.empty((0, 0), dtype=float)

    out_rows = subset.shape[0] // factor
    out_cols = subset.shape[1] // factor
    blocks = subset.reshape(out_rows, factor, out_cols, factor).transpose(0, 2, 1, 3).reshape(out_rows, out_cols, factor * factor)
    valid_counts = np.sum(~np.isnan(blocks), axis=2)

    result = np.full((out_rows, out_cols), np.nan, dtype=float)
    if aggregation == "SUM":
        result = np.nansum(blocks, axis=2)
    elif aggregation == "MAXIMUM":
        for row in range(out_rows):
            for col in range(out_cols):
                values = blocks[row, col]
                valid = values[~np.isnan(values)]
                if valid.size != 0:
                    result[row, col] = float(np.max(valid))
    elif aggregation == "MEAN":
        result = np.nanmean(blocks, axis=2)
    elif aggregation == "MEDIAN":
        result = np.nanmedian(blocks, axis=2)
    elif aggregation == "MINIMUM":
        for row in range(out_rows):
            for col in range(out_cols):
                values = blocks[row, col]
                valid = values[~np.isnan(values)]
                if valid.size != 0:
                    result[row, col] = float(np.min(valid))

    required_count = factor * factor
    if nodata_mode == "NODATA":
        result[valid_counts != required_count] = np.nan
    else:
        result[valid_counts == 0] = np.nan

    return result


def _cell_offset(delta, cell_size):
    return int(round(float(delta) / float(cell_size)))


def _valid_data_mask(array, nodata):
    values = np.asarray(array, dtype=float)
    mask = ~np.isnan(values)
    if nodata is None:
        return mask
    try:
        if np.isnan(nodata):
            return mask
    except TypeError:
        pass
    return mask & (values != float(nodata))


def _get_raster_label(raster):
    path = _get_raster_path(raster)
    return os.path.basename(path) if path not in [None, ""] else str(raster)


def _get_raster_basename(raster):
    path = _get_raster_path(raster)
    base_name = os.path.basename(path)
    return base_name if base_name not in ["", None] else "aggregated_raster.tif"


def _get_raster_path(raster):
    if hasattr(raster, "source"):
        return str(raster.source()).split("|", 1)[0]
    if hasattr(raster, "catalogPath"):
        return str(raster.catalogPath)
    return str(raster)


def _resolve_output_nodata(nodata):
    try:
        if nodata is None or np.isnan(nodata):
            return -9999.0
    except TypeError:
        if nodata is None:
            return -9999.0
    return float(nodata)


def _replace_nan(array, fill_value):
    return np.where(np.isnan(array), float(fill_value), array)


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


def _add_message(messages, text):
    if messages is not None:
        messages.add_message(text)


def _add_error(messages, text):
    if messages is not None:
        messages.add_error(text)
    raise ValueError(text)
