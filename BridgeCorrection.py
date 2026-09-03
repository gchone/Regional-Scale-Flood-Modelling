from __future__ import annotations

import os
import uuid

import numpy as np


def execute_BridgeCorrection(dem_raster, bridges, output_path, GIStools=None, messages=None, language="EN"):
    del language
    if GIStools is None:
        GIStools = _autodetect_gistools()

    dem_data = GIStools.RasterAccess.read_raster_grid(dem_raster)
    dem_array = np.asarray(dem_data["array"], dtype=float)
    dem_nodata = _resolve_output_nodata(dem_data.get("nodata"))

    workspace = os.path.dirname(str(output_path))
    bridge_raster_path = _build_temp_raster_path(workspace, "bridgezones")
    fill_seed_path = _build_temp_raster_path(workspace, "bridgefill")
    filled_path = _build_temp_raster_path(workspace, "bridgefilled")

    try:
        GIStools.Geoprocessing.rasterize_polygons_with_boundaries(
            bridges,
            dem_raster,
            dem_data,
            bridge_raster_path,
        )
        bridge_data = GIStools.RasterAccess.read_raster_grid(bridge_raster_path)
        bridge_array = np.asarray(bridge_data["array"], dtype=float)
        bridge_mask = _valid_data_mask(bridge_array, bridge_data.get("nodata"))

        if not np.any(bridge_mask):
            GIStools.RasterAccess.write_raster_grid(
                dem_data,
                _replace_nan(dem_array, dem_nodata),
                output_path,
                nodata=dem_nodata,
            )
            _add_message(messages, "No bridge pixels found; copied DEM unchanged.")
            return output_path

        fill_seed = np.array(dem_array, copy=True)
        fill_mask = np.zeros(dem_array.shape, dtype=bool)

        for raw_zone_id in np.unique(bridge_array[bridge_mask]):
            zone_id = int(round(float(raw_zone_id)))
            zone_mask = bridge_mask & np.isclose(bridge_array, float(zone_id))
            zone_values = dem_array[zone_mask]
            zone_valid_mask = _valid_data_mask(zone_values, dem_data.get("nodata"))
            if not np.any(zone_valid_mask):
                _add_warning(messages, f"Bridge zone {zone_id} has no valid DEM values; leaving it unchanged.")
                continue

            zone_min = float(np.min(zone_values[zone_valid_mask]))
            fill_seed[zone_mask] = zone_min
            fill_mask |= zone_mask

        if not np.any(fill_mask):
            GIStools.RasterAccess.write_raster_grid(
                dem_data,
                _replace_nan(dem_array, dem_nodata),
                output_path,
                nodata=dem_nodata,
            )
            _add_warning(messages, "Bridge zones contained no usable DEM values; copied DEM unchanged.")
            return output_path

        GIStools.RasterAccess.write_raster_grid(
            dem_data,
            _replace_nan(fill_seed, dem_nodata),
            fill_seed_path,
            nodata=dem_nodata,
        )
        GIStools.Geoprocessing.fill_dem(fill_seed_path, filled_path)
        filled_data = GIStools.RasterAccess.read_raster_grid(filled_path)
        filled_array = np.asarray(filled_data["array"], dtype=float)

        result = np.array(dem_array, copy=True)
        result[fill_mask] = filled_array[fill_mask]
        GIStools.RasterAccess.write_raster_grid(
            dem_data,
            _replace_nan(result, dem_nodata),
            output_path,
            nodata=dem_nodata,
        )
        _add_message(messages, "Bridge correction complete.")
        return output_path
    finally:
        for temp_path in [bridge_raster_path, fill_seed_path, filled_path]:
            GIStools.Geoprocessing.delete_dataset(temp_path)


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


def _build_temp_raster_path(workspace, stem):
    workspace = str(workspace or os.getcwd())
    name = f"_{stem}_{uuid.uuid4().hex}"
    if workspace.lower().endswith(".gdb"):
        return os.path.join(workspace, name)
    return os.path.join(workspace, name + ".tif")


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
