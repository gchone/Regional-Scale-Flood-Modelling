from __future__ import annotations

import math
import os
import uuid

import numpy as np


WALL_HEIGHT = 10000.0


def execute_FlowDirectionForWS(routes_main, DEM3m_forws, DEMs_footprints, output_workspace, exit_dist, messages=None, GIStools=None):
    if GIStools is None:
        GIStools = _autodetect_gistools()

    if not str(output_workspace).lower().endswith(".gdb") and not os.path.isdir(output_workspace):
        os.makedirs(output_workspace)

    results = []
    for index, footprint_row in enumerate(GIStools.DataManagement.read_attribute_table(DEMs_footprints, [])):
        footprint_oid = _get_feature_oid(footprint_row, index)
        temp_clip = _build_temp_raster_path(output_workspace, f"demclip_{footprint_oid}")
        temp_walled = _build_temp_raster_path(output_workspace, f"walled_{footprint_oid}")
        temp_filled = _build_temp_raster_path(output_workspace, f"filled_{footprint_oid}")
        temp_flowdir = _build_temp_raster_path(output_workspace, f"flowdir_{footprint_oid}")

        try:
            GIStools.Geoprocessing.clip_raster_to_feature(
                DEM3m_forws,
                DEMs_footprints,
                footprint_oid,
                temp_clip,
            )
            clipped_data = GIStools.RasterAccess.read_raster_grid(temp_clip)
            clipped_array = np.asarray(clipped_data["array"], dtype=float)
            nodata_value = _resolve_output_nodata(clipped_data.get("nodata"))
            valid_mask = _valid_data_mask(clipped_array, clipped_data.get("nodata"))

            if not np.any(valid_mask):
                _add_warning(messages, f"Footprint {footprint_oid} contains no valid DEM pixels; skipped.")
                continue

            expanded_reference = _expand_reference_grid(clipped_data, 1)
            expanded_array = np.full((clipped_array.shape[0] + 2, clipped_array.shape[1] + 2), nodata_value, dtype=float)
            expanded_valid_mask = np.zeros(expanded_array.shape, dtype=bool)
            expanded_array[1:-1, 1:-1] = clipped_array
            expanded_valid_mask[1:-1, 1:-1] = valid_mask

            wall_mask = _dilate_mask(expanded_valid_mask)
            exit_points = GIStools.Geoprocessing.collect_intersection_start_points(
                routes_main,
                DEMs_footprints,
                footprint_oid,
            )
            exit_mask = _rasterize_buffered_points(exit_points, expanded_reference, expanded_valid_mask.shape, float(exit_dist))

            walled_array = np.full(expanded_array.shape, nodata_value, dtype=float)
            walled_array[wall_mask] = WALL_HEIGHT
            walled_array[expanded_valid_mask] = expanded_array[expanded_valid_mask]
            walled_array[exit_mask] = nodata_value

            GIStools.RasterAccess.write_raster_grid(
                expanded_reference,
                _replace_nan(walled_array, nodata_value),
                temp_walled,
                nodata=nodata_value,
            )
            GIStools.Geoprocessing.fill_dem(temp_walled, temp_filled)
            GIStools.Geoprocessing.compute_flow_direction(temp_filled, temp_flowdir)

            flowdir_data = GIStools.RasterAccess.read_raster_grid(temp_flowdir)
            flowdir_array = _coerce_shape(np.asarray(flowdir_data["array"], dtype=float), walled_array.shape, nodata_value)
            cropped_flowdir = flowdir_array[1:-1, 1:-1]

            result_array = np.full(clipped_array.shape, nodata_value, dtype=float)
            result_array[valid_mask] = cropped_flowdir[valid_mask]

            output_path = _build_output_raster_path(output_workspace, f"dem{footprint_oid}")
            GIStools.RasterAccess.write_raster_grid(
                clipped_data,
                _replace_nan(result_array, nodata_value),
                output_path,
                nodata=nodata_value,
            )
            results.append(output_path)
            _add_message(messages, f"Done DEM with footprint id {footprint_oid}")
        finally:
            for temp_path in [temp_clip, temp_walled, temp_filled, temp_flowdir]:
                GIStools.Geoprocessing.delete_dataset(temp_path)

    return results


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


def _get_feature_oid(feature_row, fallback_index):
    try:
        return int(feature_row.get_oid())
    except Exception:
        feature = getattr(feature_row, "line", None)
        if feature is not None and hasattr(feature, "id"):
            try:
                return int(feature.id())
            except Exception:
                return int(fallback_index)
    return int(fallback_index)


def _build_temp_raster_path(workspace, stem):
    workspace = str(workspace or os.getcwd())
    name = f"_{stem}_{uuid.uuid4().hex}"
    if workspace.lower().endswith(".gdb"):
        return os.path.join(workspace, name)
    return os.path.join(workspace, name + ".tif")


def _build_output_raster_path(workspace, stem):
    if str(workspace).lower().endswith(".gdb"):
        return os.path.join(workspace, stem)
    return os.path.join(workspace, stem + ".tif")


def _expand_reference_grid(reference_grid, border_cells):
    expanded = dict(reference_grid)
    pixel_width = float(reference_grid["pixel_width"])
    pixel_height = float(reference_grid["pixel_height"])
    width = int(reference_grid["width"]) + 2 * int(border_cells)
    height = int(reference_grid["height"]) + 2 * int(border_cells)
    x_min = float(reference_grid["x_min"]) - border_cells * pixel_width
    y_max = float(reference_grid["y_max"]) + border_cells * pixel_height
    y_min = y_max - height * pixel_height

    expanded["x_min"] = x_min
    expanded["y_max"] = y_max
    expanded["y_min"] = y_min
    expanded["width"] = width
    expanded["height"] = height
    return expanded


def _dilate_mask(mask):
    dilated = np.zeros(mask.shape, dtype=bool)
    for row_offset in (-1, 0, 1):
        for col_offset in (-1, 0, 1):
            src_row_start = max(0, -row_offset)
            src_row_end = mask.shape[0] - max(0, row_offset)
            src_col_start = max(0, -col_offset)
            src_col_end = mask.shape[1] - max(0, col_offset)
            dst_row_start = max(0, row_offset)
            dst_row_end = mask.shape[0] - max(0, -row_offset)
            dst_col_start = max(0, col_offset)
            dst_col_end = mask.shape[1] - max(0, -col_offset)
            dilated[dst_row_start:dst_row_end, dst_col_start:dst_col_end] |= mask[src_row_start:src_row_end, src_col_start:src_col_end]
    return dilated


def _rasterize_buffered_points(points, reference_grid, shape, radius):
    mask = np.zeros(shape, dtype=bool)
    if radius <= 0:
        return mask

    pixel_width = float(reference_grid["pixel_width"])
    pixel_height = float(reference_grid["pixel_height"])
    x_min = float(reference_grid["x_min"])
    y_min = float(reference_grid["y_min"])
    y_max = float(reference_grid["y_max"])
    rows, cols = shape
    col_radius = int(math.ceil(radius / pixel_width))
    row_radius = int(math.ceil(radius / pixel_height))

    for point in points:
        point_x = float(point["x"])
        point_y = float(point["y"])
        center_col = int(math.floor((point_x - x_min) / pixel_width))
        center_row = int(rows - math.floor((point_y - y_min) / pixel_height) - 1)

        if center_col < -col_radius or center_col >= cols + col_radius or center_row < -row_radius or center_row >= rows + row_radius:
            continue

        row_start = max(0, center_row - row_radius)
        row_end = min(rows, center_row + row_radius + 1)
        col_start = max(0, center_col - col_radius)
        col_end = min(cols, center_col + col_radius + 1)

        for row in range(row_start, row_end):
            cell_y = y_max - (float(row) + 0.5) * pixel_height
            for col in range(col_start, col_end):
                cell_x = x_min + (float(col) + 0.5) * pixel_width
                if math.hypot(cell_x - point_x, cell_y - point_y) <= radius:
                    mask[row, col] = True

    return mask


def _coerce_shape(array, shape, fill_value):
    if array.shape == shape:
        return array
    result = np.full(shape, fill_value, dtype=float)
    rows = min(shape[0], array.shape[0])
    cols = min(shape[1], array.shape[1])
    result[:rows, :cols] = array[:rows, :cols]
    return result


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


def _add_message(messages, text):
    if messages is not None:
        messages.add_message(text)


def _add_warning(messages, text):
    if messages is not None:
        messages.add_warning(text)
