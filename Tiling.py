from __future__ import annotations

import math
import os

import numpy as np


VALID_D8_DIRECTIONS = {1, 2, 4, 8, 16, 32, 64, 128}
SEGMENT_NODATA = -255


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

    def x_to_col(self, x_value):
        return int(math.floor((float(x_value) - self.x_min) / self.pixel_width))

    def y_to_row(self, y_value):
        return int(self.height - math.floor((float(y_value) - self.y_min) / self.pixel_height) - 1)

    def col_to_x(self, col_value):
        return self.x_min + (float(col_value) + 0.5) * self.pixel_width

    def row_to_y(self, row_value):
        return self.y_max - (float(row_value) + 0.5) * self.pixel_height

    def in_bounds(self, row_value, col_value):
        return 0 <= row_value < self.height and 0 <= col_value < self.width

    def get_value(self, row_value, col_value):
        if not self.in_bounds(row_value, col_value):
            return None
        value = self.array[row_value, col_value]
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


class PointFlowPath:
    pass


class BoundingBoxPolygonLookup:
    def __init__(self, records):
        self.records = list(records)

    def find_containing_feature(self, x_value, y_value):
        for record in self.records:
            if (
                record["XMin"] <= x_value <= record["XMax"]
                and record["YMin"] <= y_value <= record["YMax"]
            ):
                return record
        return None


def execute_create_zones(flowdir_raster, lakes, frompoint, distance, bufferw, out_folder, GIStools, messages):
    if GIStools is None:
        raise ValueError("A GIStools package must be provided.")

    if not os.path.isdir(out_folder):
        os.makedirs(out_folder)

    flowdir_data = GIStools.RasterAccess.read_raster_grid(flowdir_raster)
    flowdir_grid = RasterGrid.from_raster_data(flowdir_data)

    lakes_raster_path = os.path.join(out_folder, "r_lakes.tif")
    GIStools.Geoprocessing.rasterize_polygons_to_match(lakes, flowdir_raster, flowdir_data, lakes_raster_path)
    lakes_data = GIStools.RasterAccess.read_raster_grid(lakes_raster_path)
    lakes_grid = RasterGrid.from_raster_data(lakes_data)

    try:
        flowdir_grid.check_match(lakes_grid)
    except ValueError as exc:
        messages.add_error(str(exc))

    polygon_lookup = GIStools.DataManagement.build_polygon_lookup(lakes)
    from_points = _load_from_points(frompoint, GIStools)

    segmentation = segment_flow_paths(
        flowdir_grid,
        lakes_grid,
        from_points,
        int(distance),
        polygon_lookup,
    )

    segments_path = os.path.join(out_folder, "segments.tif")
    GIStools.RasterAccess.write_integer_raster_grid(flowdir_data, segmentation["segments_array"], segments_path, nodata=SEGMENT_NODATA)

    buffered_segment_data = GIStools.Geoprocessing.build_tiling_buffer_extents(segments_path, bufferw, out_folder)
    zone_records = build_zone_records(
        buffered_segment_data["records"],
        segmentation["lakes_bci"],
        segmentation["toclip"],
    )
    source_records = build_source_records(segmentation["input_points"])
    spatial_reference = GIStools.RasterAccess.get_raster_spatial_reference(flowdir_raster)

    polyzones_path = GIStools.DataManagement.write_tiling_polygons(out_folder, zone_records, spatial_reference)
    sourcepoints_path = GIStools.DataManagement.write_tiling_source_points(out_folder, source_records, spatial_reference)

    if messages is not None:
        messages.add_message(f"Saved polyzones to {polyzones_path}")
        messages.add_message(f"Saved sourcepoints to {sourcepoints_path}")
        messages.add_message("Tiling complete.")

    return {
        "segments": segments_path,
        "polyzones": polyzones_path,
        "sourcepoints": sourcepoints_path,
    }


def segment_flow_paths(flowdir_grid, lake_grid, from_points, distance, polygon_lookup):
    flowdir_grid.check_match(lake_grid)

    segments_array = np.full((flowdir_grid.height, flowdir_grid.width), int(SEGMENT_NODATA), dtype=np.int32)
    segnumber = 0
    lakes_bci = {}
    toclip = {}
    input_points = {}

    for from_point in from_points:
        segnumber += 1
        current_col = flowdir_grid.x_to_col(from_point["x"])
        current_row = flowdir_grid.y_to_row(from_point["y"])

        in_raster = True
        if not flowdir_grid.in_bounds(current_row, current_col):
            in_raster = False
        elif _get_direction(flowdir_grid, current_row, current_col) not in VALID_D8_DIRECTIONS:
            in_raster = False

        listpointsflowpath = []
        totaldistance = 0.0
        currentdistance = 0.0
        inlake = True
        dividedriver = False
        listtomerged = []

        while in_raster:
            waslake = inlake
            inlake = lake_grid.get_value(current_row, current_col) is not None

            if not (inlake and waslake):
                totaldistance = totaldistance + currentdistance

            if inlake and not waslake:
                coord_x = flowdir_grid.col_to_x(current_col)
                coord_y = flowdir_grid.row_to_y(current_row)
                lake_record = polygon_lookup.find_containing_feature(coord_x, coord_y)

                if lake_record is not None:
                    lakes_bci[segnumber] = lake_record["_oid"]
                    clip_item = _build_clip_item(coord_x, coord_y, lake_record)
                    if clip_item is not None:
                        toclip[segnumber] = clip_item

                if totaldistance < 0.3 * distance and dividedriver:
                    if segnumber in toclip:
                        toclip[segnumber - 1] = toclip.pop(segnumber)
                    listtomerged.append(segnumber)
                totaldistance = 0.0
                segnumber += 1
                dividedriver = False

            elif totaldistance > distance:
                totaldistance = 0.0
                segnumber += 1
                dividedriver = True

            if not inlake:
                currentpoint = PointFlowPath()
                currentpoint.row = current_row
                currentpoint.col = current_col
                currentpoint.X = flowdir_grid.col_to_x(current_col)
                currentpoint.Y = flowdir_grid.row_to_y(current_row)
                currentpoint.distance = totaldistance
                currentpoint.segnumber = segnumber
                currentpoint.frompointid = from_point["id"]
                listpointsflowpath.append(currentpoint)

            next_step = _step_from_direction(flowdir_grid, current_row, current_col)
            if next_step is None:
                in_raster = False
            else:
                current_row, current_col, currentdistance = next_step

            if in_raster:
                if not flowdir_grid.in_bounds(current_row, current_col):
                    in_raster = False
                elif _get_direction(flowdir_grid, current_row, current_col) not in VALID_D8_DIRECTIONS:
                    in_raster = False

            if in_raster:
                confluence_seg = int(segments_array[current_row, current_col])
                if confluence_seg != int(SEGMENT_NODATA):
                    if confluence_seg in listtomerged:
                        confluence_seg -= 1
                    if confluence_seg in toclip:
                        toclip[segnumber] = list(toclip[confluence_seg])
                    if totaldistance < 0.3 * distance and dividedriver:
                        listtomerged.append(segnumber)
                        if segnumber in toclip:
                            toclip[segnumber - 1] = toclip.pop(segnumber)
                    in_raster = False

        for currentpoint in listpointsflowpath:
            if currentpoint.segnumber in listtomerged:
                currentpoint.segnumber -= 1
            segments_array[currentpoint.row, currentpoint.col] = currentpoint.segnumber
            if currentpoint.segnumber not in input_points:
                newpoint = PointFlowPath()
                newpoint.type = "main"
                newpoint.frompointid = currentpoint.frompointid
                newpoint.X = currentpoint.X
                newpoint.Y = currentpoint.Y
                input_points[currentpoint.segnumber] = newpoint

        for merged_segment in list(listtomerged):
            if merged_segment in lakes_bci:
                lakes_bci[merged_segment - 1] = lakes_bci.pop(merged_segment)
            if merged_segment in toclip:
                toclip[merged_segment - 1] = toclip.pop(merged_segment)

    return {
        "segments_array": segments_array,
        "lakes_bci": lakes_bci,
        "toclip": toclip,
        "input_points": input_points,
    }


def build_zone_records(buffered_segment_records, lakes_bci, toclip):
    zone_records = []
    for segment_record in buffered_segment_records:
        grid_code = int(segment_record["GRID_CODE"])
        xmin = float(segment_record["XMin"])
        ymin = float(segment_record["YMin"])
        xmax = float(segment_record["XMax"])
        ymax = float(segment_record["YMax"])

        if grid_code in toclip:
            clip_type, clip_value = toclip[grid_code]
            if clip_type == "Xmin":
                xmin = max(float(clip_value), xmin)
            if clip_type == "Xmax":
                xmax = min(float(clip_value), xmax)
            if clip_type == "Ymin":
                ymin = max(float(clip_value), ymin)
            if clip_type == "Ymax":
                ymax = min(float(clip_value), ymax)

        zone_records.append({
            "GRID_CODE": grid_code,
            "Lake_ID": int(lakes_bci.get(grid_code, -999)),
            "XMin": xmin,
            "YMin": ymin,
            "XMax": xmax,
            "YMax": ymax,
        })

    return zone_records


def build_source_records(input_points):
    records = []
    for zone_id in sorted(input_points):
        point = input_points[zone_id]
        records.append({
            "ZoneID": int(zone_id),
            "fpid": int(point.frompointid),
            "X": float(point.X),
            "Y": float(point.Y),
        })
    return records


def _load_from_points(frompoint, GIStools):
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
    return from_points


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


def _build_clip_item(coord_x, coord_y, lake_record):
    dist_xmin = abs(coord_x - float(lake_record["XMin"]))
    dist_xmax = abs(coord_x - float(lake_record["XMax"]))
    dist_ymin = abs(coord_y - float(lake_record["YMin"]))
    dist_ymax = abs(coord_y - float(lake_record["YMax"]))
    minimum = min(dist_xmin, dist_xmax, dist_ymin, dist_ymax)

    clip_item = None
    if minimum == dist_xmin:
        clip_item = ["Xmax", float(lake_record["XMin"])]
    if minimum == dist_xmax:
        clip_item = ["Xmin", float(lake_record["XMax"])]
    if minimum == dist_ymin:
        clip_item = ["Ymax", float(lake_record["YMin"])]
    if minimum == dist_ymax:
        clip_item = ["Ymin", float(lake_record["YMax"])]
    return clip_item


def _get_direction(flowdir_grid, row_value, col_value):
    value = flowdir_grid.get_value(row_value, col_value)
    if value is None:
        return None
    try:
        direction = int(value)
    except (TypeError, ValueError):
        return None
    if direction not in VALID_D8_DIRECTIONS:
        return None
    return direction


def _step_from_direction(flowdir_grid, row_value, col_value):
    direction = _get_direction(flowdir_grid, row_value, col_value)
    if direction is None:
        return None

    diagonal_distance = math.hypot(flowdir_grid.pixel_width, flowdir_grid.pixel_height)
    if direction == 1:
        return row_value, col_value + 1, flowdir_grid.pixel_width
    if direction == 2:
        return row_value + 1, col_value + 1, diagonal_distance
    if direction == 4:
        return row_value + 1, col_value, flowdir_grid.pixel_height
    if direction == 8:
        return row_value + 1, col_value - 1, diagonal_distance
    if direction == 16:
        return row_value, col_value - 1, flowdir_grid.pixel_width
    if direction == 32:
        return row_value - 1, col_value - 1, diagonal_distance
    if direction == 64:
        return row_value - 1, col_value, flowdir_grid.pixel_height
    return row_value - 1, col_value + 1, diagonal_distance


def _same_value(left, right):
    try:
        if np.isnan(left) and np.isnan(right):
            return True
    except TypeError:
        pass
    return left == right
