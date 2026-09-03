from __future__ import annotations

from pathlib import Path
import sys
import math
import numpy as np
import arcpy


_LEGACY_ARCGIS_DIR = Path(__file__).resolve().parents[1] / "Regional-Scale-Flood-Modelling-ArcGIS"
if str(_LEGACY_ARCGIS_DIR) not in sys.path:
    sys.path.append(str(_LEGACY_ARCGIS_DIR))

from .RasterIO import RasterIO


class FlowDirectionRaster:
    VALID_DIRS = {1, 2, 4, 8, 16, 32, 64, 128}

    def __init__(self, raster):
        self._raster_io = RasterIO(raster)
        self.raster = self._raster_io.raster

    def x_to_col(self, x: float) -> int:
        return int(self._raster_io.XtoCol(x))

    def y_to_row(self, y: float) -> int:
        return int(self._raster_io.YtoRow(y))

    def col_to_x(self, col: int) -> float:
        return float(self._raster_io.ColtoX(col))

    def row_to_y(self, row: int) -> float:
        return float(self._raster_io.RowtoY(row))

    def in_bounds(self, row: int, col: int) -> bool:
        return 0 <= row < self.raster.height and 0 <= col < self.raster.width

    def get_value(self, row: int, col: int) -> int:
        return int(self._raster_io.getValue(row, col))

    def step(self, row: int, col: int) -> tuple[int, int, float] | None:
        direction = self.get_value(row, col)
        if direction not in self.VALID_DIRS:
            return None
        if direction == 1:
            return row, col + 1, float(self.raster.meanCellWidth)
        if direction == 2:
            return row + 1, col + 1, float(math.hypot(self.raster.meanCellWidth, self.raster.meanCellHeight))
        if direction == 4:
            return row + 1, col, float(self.raster.meanCellHeight)
        if direction == 8:
            return row + 1, col - 1, float(math.hypot(self.raster.meanCellWidth, self.raster.meanCellHeight))
        if direction == 16:
            return row, col - 1, float(self.raster.meanCellWidth)
        if direction == 32:
            return row - 1, col - 1, float(math.hypot(self.raster.meanCellWidth, self.raster.meanCellHeight))
        if direction == 64:
            return row - 1, col, float(self.raster.meanCellHeight)
        return row - 1, col + 1, float(math.hypot(self.raster.meanCellWidth, self.raster.meanCellHeight))


def read_raster_grid(raster):
    raster_obj = raster if hasattr(raster, "extent") else arcpy.Raster(raster)
    array = np.asarray(arcpy.RasterToNumPyArray(raster_obj), dtype=float)
    return {
        "array": array,
        "width": int(raster_obj.width),
        "height": int(raster_obj.height),
        "x_min": float(raster_obj.extent.XMin),
        "y_min": float(raster_obj.extent.YMin),
        "y_max": float(raster_obj.extent.YMax),
        "pixel_width": float(raster_obj.meanCellWidth),
        "pixel_height": float(raster_obj.meanCellHeight),
        "nodata": raster_obj.noDataValue,
        "spatial_reference": raster_obj.spatialReference,
        "reference_raster": raster_obj,
    }


def write_raster_grid(reference_grid, array, output_path, nodata=-255.0):
    result_array = np.asarray(array, dtype=np.float32)
    raster = arcpy.NumPyArrayToRaster(
        result_array,
        arcpy.Point(reference_grid["x_min"], reference_grid["y_min"]),
        float(reference_grid["pixel_width"]),
        float(reference_grid["pixel_height"]),
        nodata,
    )
    raster.save(output_path)
    spatial_reference = reference_grid.get("spatial_reference")
    if spatial_reference is not None:
        arcpy.DefineProjection_management(output_path, spatial_reference)
    return output_path


def get_raster_spatial_reference(raster):
    raster_obj = raster if hasattr(raster, "spatialReference") else arcpy.Raster(raster)
    return raster_obj.spatialReference


def write_integer_raster_grid(reference_grid, array, output_path, nodata=-255):
    result_array = np.asarray(array, dtype=np.int32)
    raster = arcpy.NumPyArrayToRaster(
        result_array,
        arcpy.Point(reference_grid["x_min"], reference_grid["y_min"]),
        float(reference_grid["pixel_width"]),
        float(reference_grid["pixel_height"]),
        int(nodata),
    )
    raster.save(output_path)
    spatial_reference = reference_grid.get("spatial_reference")
    if spatial_reference is not None:
        arcpy.DefineProjection_management(output_path, spatial_reference)
    return output_path
