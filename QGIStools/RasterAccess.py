from __future__ import annotations

import math
import numpy as np

from osgeo import gdal


class FlowDirectionRaster:
    VALID_DIRS = {1, 2, 4, 8, 16, 32, 64, 128}
    D8_STEPS = {
        1: (0, 1),
        2: (1, 1),
        4: (1, 0),
        8: (1, -1),
        16: (0, -1),
        32: (-1, -1),
        64: (-1, 0),
        128: (-1, 1),
    }

    def __init__(self, raster_layer):
        path = raster_layer.source() if hasattr(raster_layer, "source") else raster_layer
        dataset = gdal.Open(path, gdal.GA_ReadOnly)
        if dataset is None:
            raise ValueError(f"GDAL could not open flow direction raster: {path}")
        self.array = dataset.GetRasterBand(1).ReadAsArray()
        self.height, self.width = self.array.shape
        transform = dataset.GetGeoTransform()
        self.xmin = transform[0]
        self.ymax = transform[3]
        self.pixel_w = abs(transform[1])
        self.pixel_h = abs(transform[5])
        dataset = None

    def x_to_col(self, x: float) -> int:
        return int((x - self.xmin) / self.pixel_w)

    def y_to_row(self, y: float) -> int:
        return int((self.ymax - y) / self.pixel_h)

    def col_to_x(self, col: int) -> float:
        return self.xmin + (col + 0.5) * self.pixel_w

    def row_to_y(self, row: int) -> float:
        return self.ymax - (row + 0.5) * self.pixel_h

    def in_bounds(self, row: int, col: int) -> bool:
        return 0 <= row < self.height and 0 <= col < self.width

    def get_value(self, row: int, col: int) -> int:
        return int(self.array[row, col])

    def step(self, row: int, col: int) -> tuple[int, int, float] | None:
        direction = self.get_value(row, col)
        if direction not in self.VALID_DIRS:
            return None
        row_delta, col_delta = self.D8_STEPS[direction]
        next_row = row + row_delta
        next_col = col + col_delta
        if row_delta != 0 and col_delta != 0:
            distance = math.hypot(self.pixel_w, self.pixel_h)
        elif col_delta != 0:
            distance = self.pixel_w
        else:
            distance = self.pixel_h
        return next_row, next_col, distance


def read_raster_grid(raster_layer):
    path = raster_layer.source() if hasattr(raster_layer, "source") else raster_layer
    dataset = gdal.Open(path, gdal.GA_ReadOnly)
    if dataset is None:
        raise ValueError(f"GDAL could not open raster: {path}")

    band = dataset.GetRasterBand(1)
    transform = dataset.GetGeoTransform()
    pixel_width = abs(transform[1])
    pixel_height = abs(transform[5])
    y_max = transform[3]
    y_min = y_max - dataset.RasterYSize * pixel_height
    projection = dataset.GetProjection()
    array = np.asarray(band.ReadAsArray(), dtype=float)
    nodata = band.GetNoDataValue()
    dataset = None

    return {
        "array": array,
        "width": int(array.shape[1]),
        "height": int(array.shape[0]),
        "x_min": float(transform[0]),
        "y_min": float(y_min),
        "y_max": float(y_max),
        "pixel_width": float(pixel_width),
        "pixel_height": float(pixel_height),
        "nodata": nodata,
        "projection": projection,
    }


def write_raster_grid(reference_grid, array, output_path, nodata=-255.0):
    result_array = np.asarray(array, dtype=np.float32)
    driver = gdal.GetDriverByName("GTiff")
    dataset = driver.Create(
        str(output_path),
        int(reference_grid["width"]),
        int(reference_grid["height"]),
        1,
        gdal.GDT_Float32,
    )
    if dataset is None:
        raise ValueError(f"GDAL could not create raster: {output_path}")

    dataset.SetGeoTransform((
        float(reference_grid["x_min"]),
        float(reference_grid["pixel_width"]),
        0.0,
        float(reference_grid["y_max"]),
        0.0,
        -float(reference_grid["pixel_height"]),
    ))
    projection = reference_grid.get("projection")
    if projection not in [None, ""]:
        dataset.SetProjection(projection)

    band = dataset.GetRasterBand(1)
    band.SetNoDataValue(float(nodata))
    band.WriteArray(result_array)
    band.FlushCache()
    dataset.FlushCache()
    dataset = None
    return output_path


def get_raster_spatial_reference(raster_layer):
    if hasattr(raster_layer, "crs"):
        try:
            return raster_layer.crs()
        except Exception:
            return None
    return None


def write_integer_raster_grid(reference_grid, array, output_path, nodata=-255):
    result_array = np.asarray(array, dtype=np.int32)
    driver = gdal.GetDriverByName("GTiff")
    dataset = driver.Create(
        str(output_path),
        int(reference_grid["width"]),
        int(reference_grid["height"]),
        1,
        gdal.GDT_Int32,
    )
    if dataset is None:
        raise ValueError(f"GDAL could not create raster: {output_path}")

    dataset.SetGeoTransform((
        float(reference_grid["x_min"]),
        float(reference_grid["pixel_width"]),
        0.0,
        float(reference_grid["y_max"]),
        0.0,
        -float(reference_grid["pixel_height"]),
    ))
    projection = reference_grid.get("projection")
    if projection not in [None, ""]:
        dataset.SetProjection(projection)

    band = dataset.GetRasterBand(1)
    band.SetNoDataValue(int(nodata))
    band.WriteArray(result_array)
    band.FlushCache()
    dataset.FlushCache()
    dataset = None
    return output_path
