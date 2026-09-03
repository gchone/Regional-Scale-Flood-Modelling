from __future__ import annotations

import math

import numpy as np


VALID_D8_DIRECTIONS = {1, 2, 4, 8, 16, 32, 64, 128}
RESULT_NODATA = -255.0


class RasterGrid:
    def __init__(self, array, x_min, y_min, y_max, pixel_width, pixel_height, nodata=None):
        self.array = np.asarray(array)
        if self.array.ndim != 2:
            raise ValueError("Raster arrays must be two-dimensional.")
        self.height, self.width = self.array.shape
        self.x_min = float(x_min)
        self.y_min = float(y_min)
        self.y_max = float(y_max)
        self.pixel_width = abs(float(pixel_width))
        self.pixel_height = abs(float(pixel_height))
        self.nodata = nodata

    @classmethod
    def from_raster_data(cls, raster_data):
        return cls(
            raster_data["array"],
            raster_data["x_min"],
            raster_data["y_min"],
            raster_data["y_max"],
            raster_data["pixel_width"],
            raster_data["pixel_height"],
            raster_data.get("nodata"),
        )

    @property
    def x_max(self):
        return self.x_min + self.width * self.pixel_width

    def x_to_col(self, x):
        return int(math.floor((float(x) - self.x_min) / self.pixel_width))

    def y_to_row(self, y):
        return int(self.height - math.floor((float(y) - self.y_min) / self.pixel_height) - 1)

    def col_to_x(self, col):
        return self.x_min + (float(col) + 0.5) * self.pixel_width

    def row_to_y(self, row):
        return self.y_max - (float(row) + 0.5) * self.pixel_height

    def in_bounds(self, row, col):
        return 0 <= row < self.height and 0 <= col < self.width

    def get_value(self, row, col):
        if not self.in_bounds(row, col):
            return None
        value = self.array[row, col]
        if self.nodata is not None and _same_value(value, self.nodata):
            return None
        if isinstance(value, np.generic):
            return value.item()
        return value

    def check_match(self, other):
        if (
            round(self.x_min, 3) != round(other.x_min, 3)
            or round(self.y_min, 3) != round(other.y_min, 3)
            or round(self.x_max, 3) != round(other.x_max, 3)
            or round(self.y_max, 3) != round(other.y_max, 3)
            or self.height != other.height
            or self.width != other.width
        ):
            raise ValueError("Input rasters must have same size and resolution")


class _FrompointPaths:
    def __init__(self):
        self.donepts = {}

    def add_point(self, row, col, fp_id):
        if row not in self.donepts:
            self.donepts[row] = {}
        self.donepts[row][col] = fp_id

    def done_previously(self, row, col, fp_id):
        try:
            return self.donepts[row][col] != fp_id
        except KeyError:
            return False


def convert_d8_to_d4(flowdir_grid, dem_grid, from_points, result_nodata=RESULT_NODATA):
    dem_grid.check_match(flowdir_grid)
    result = np.full((flowdir_grid.height, flowdir_grid.width), float(result_nodata), dtype=float)
    donepoints = _FrompointPaths()

    for from_point in from_points:
        current_col = flowdir_grid.x_to_col(from_point["x"])
        current_row = flowdir_grid.y_to_row(from_point["y"])
        fp_id = from_point["id"]

        in_raster = True
        if not flowdir_grid.in_bounds(current_row, current_col):
            in_raster = False
        elif _get_direction(flowdir_grid, current_row, current_col) not in VALID_D8_DIRECTIONS:
            in_raster = False

        while in_raster:
            direction = _get_direction(flowdir_grid, current_row, current_col)
            donepoints.add_point(current_row, current_col, fp_id)

            if direction == 1:
                result[current_row, current_col] = direction
                current_col = current_col + 1

            if direction == 2:
                if dem_grid.get_value(current_row, current_col + 1) is None:
                    result[current_row, current_col] = 1
                    in_raster = False
                elif dem_grid.get_value(current_row + 1, current_col) is None:
                    result[current_row, current_col] = 4
                    in_raster = False
                elif dem_grid.get_value(current_row, current_col + 1) < dem_grid.get_value(current_row + 1, current_col):
                    result[current_row, current_col] = 1
                    if donepoints.done_previously(current_row, current_col + 1, fp_id):
                        in_raster = False
                    else:
                        result[current_row, current_col + 1] = 4
                        donepoints.add_point(current_row, current_col + 1, fp_id)
                else:
                    result[current_row, current_col] = 4
                    if donepoints.done_previously(current_row + 1, current_col, fp_id):
                        in_raster = False
                    else:
                        result[current_row + 1, current_col] = 1
                        donepoints.add_point(current_row + 1, current_col, fp_id)
                current_col = current_col + 1
                current_row = current_row + 1

            if direction == 4:
                result[current_row, current_col] = direction
                current_row = current_row + 1

            if direction == 8:
                if dem_grid.get_value(current_row + 1, current_col) is None:
                    result[current_row, current_col] = 4
                    in_raster = False
                elif dem_grid.get_value(current_row, current_col - 1) is None:
                    result[current_row, current_col] = 16
                    in_raster = False
                elif dem_grid.get_value(current_row + 1, current_col) < dem_grid.get_value(current_row, current_col - 1):
                    result[current_row, current_col] = 4
                    if donepoints.done_previously(current_row + 1, current_col, fp_id):
                        in_raster = False
                    else:
                        result[current_row + 1, current_col] = 16
                        donepoints.add_point(current_row + 1, current_col, fp_id)
                else:
                    result[current_row, current_col] = 16
                    if donepoints.done_previously(current_row, current_col - 1, fp_id):
                        in_raster = False
                    else:
                        result[current_row, current_col - 1] = 4
                        donepoints.add_point(current_row, current_col - 1, fp_id)
                current_col = current_col - 1
                current_row = current_row + 1

            if direction == 16:
                result[current_row, current_col] = direction
                current_col = current_col - 1

            if direction == 32:
                if dem_grid.get_value(current_row - 1, current_col) is None:
                    result[current_row, current_col] = 64
                    in_raster = False
                elif dem_grid.get_value(current_row, current_col - 1) is None:
                    result[current_row, current_col] = 16
                    in_raster = False
                elif dem_grid.get_value(current_row - 1, current_col) < dem_grid.get_value(current_row, current_col - 1):
                    result[current_row, current_col] = 64
                    if donepoints.done_previously(current_row - 1, current_col, fp_id):
                        in_raster = False
                    else:
                        result[current_row - 1, current_col] = 16
                        donepoints.add_point(current_row - 1, current_col, fp_id)
                else:
                    result[current_row, current_col] = 16
                    if donepoints.done_previously(current_row, current_col - 1, fp_id):
                        in_raster = False
                    else:
                        result[current_row, current_col - 1] = 64
                        donepoints.add_point(current_row, current_col - 1, fp_id)
                current_col = current_col - 1
                current_row = current_row - 1

            if direction == 64:
                result[current_row, current_col] = direction
                current_row = current_row - 1

            if direction == 128:
                if dem_grid.get_value(current_row - 1, current_col) is None:
                    result[current_row, current_col] = 64
                    in_raster = False
                elif dem_grid.get_value(current_row, current_col + 1) is None:
                    result[current_row, current_col] = 1
                    in_raster = False
                elif dem_grid.get_value(current_row - 1, current_col) < dem_grid.get_value(current_row, current_col + 1):
                    result[current_row, current_col] = 64
                    if donepoints.done_previously(current_row - 1, current_col, fp_id):
                        in_raster = False
                    else:
                        result[current_row - 1, current_col] = 1
                        donepoints.add_point(current_row - 1, current_col, fp_id)
                else:
                    result[current_row, current_col] = 1
                    if donepoints.done_previously(current_row, current_col + 1, fp_id):
                        in_raster = False
                    else:
                        result[current_row, current_col + 1] = 64
                        donepoints.add_point(current_row, current_col + 1, fp_id)
                current_col = current_col + 1
                current_row = current_row - 1

            if current_col < 0 or current_col >= flowdir_grid.width or current_row < 0 or current_row >= flowdir_grid.height:
                in_raster = False
            elif _get_direction(flowdir_grid, current_row, current_col) not in VALID_D8_DIRECTIONS:
                in_raster = False

            if in_raster:
                if donepoints.done_previously(current_row, current_col, fp_id):
                    in_raster = False

    return result


def execute_D4FlowDirection(flowdir_raster, dem_raster, frompoint, output_path, GIStools, messages):
    if GIStools is None:
        raise ValueError("A GIStools package must be provided.")

    flowdir_data = GIStools.RasterAccess.read_raster_grid(flowdir_raster)
    dem_data = GIStools.RasterAccess.read_raster_grid(dem_raster)
    flowdir_grid = RasterGrid.from_raster_data(flowdir_data)
    dem_grid = RasterGrid.from_raster_data(dem_data)

    try:
        dem_grid.check_match(flowdir_grid)
    except ValueError as exc:
        messages.add_error(str(exc))

    from_points = []
    for index, frompoint_row in enumerate(GIStools.DataManagement.read_attribute_table(frompoint, [])):
        xy = _extract_point_xy(frompoint_row.get_shape())
        if xy is None:
            continue
        from_points.append({
            "x": xy[0],
            "y": xy[1],
            "id": _get_frompoint_id(frompoint_row, index),
        })

    result = convert_d8_to_d4(flowdir_grid, dem_grid, from_points, result_nodata=RESULT_NODATA)
    saved_path = GIStools.RasterAccess.write_raster_grid(flowdir_data, result, output_path, nodata=RESULT_NODATA)
    if messages is not None:
        messages.add_message("D4 flow direction complete.")
    return saved_path


def _extract_point_xy(shape):
    if shape is None:
        return None

    first_point = getattr(shape, "firstPoint", None)
    if first_point is not None and hasattr(first_point, "X") and hasattr(first_point, "Y"):
        return float(first_point.X), float(first_point.Y)

    if hasattr(shape, "asPoint"):
        point = shape.asPoint()
        if point is None:
            return None
        x_getter = getattr(point, "x", None)
        y_getter = getattr(point, "y", None)
        if callable(x_getter) and callable(y_getter):
            return float(x_getter()), float(y_getter())

    x_getter = getattr(shape, "x", None)
    y_getter = getattr(shape, "y", None)
    if callable(x_getter) and callable(y_getter):
        return float(x_getter()), float(y_getter())

    if hasattr(shape, "X") and hasattr(shape, "Y"):
        return float(shape.X), float(shape.Y)

    if isinstance(shape, (list, tuple)) and len(shape) >= 2:
        return float(shape[0]), float(shape[1])

    return None


def _get_frompoint_id(frompoint_row, fallback_id):
    try:
        return frompoint_row.get_oid()
    except Exception:
        feature = getattr(frompoint_row, "line", None)
        if feature is not None and hasattr(feature, "id"):
            try:
                return feature.id()
            except Exception:
                return fallback_id
    return fallback_id


def _get_direction(flowdir_grid, row, col):
    value = flowdir_grid.get_value(row, col)
    if value is None:
        return None
    try:
        direction = int(value)
    except (TypeError, ValueError):
        return None
    if direction not in VALID_D8_DIRECTIONS:
        return None
    return direction


def _same_value(left, right):
    try:
        if np.isnan(left) and np.isnan(right):
            return True
    except TypeError:
        pass
    return left == right
