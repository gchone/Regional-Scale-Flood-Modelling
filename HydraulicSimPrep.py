from __future__ import annotations

from collections import defaultdict
import os

from Tiling import RasterGrid, VALID_D8_DIRECTIONS


class _Point:
    __slots__ = ("type", "frompointid", "x", "y", "numzone", "flowacc", "side")


def prepare_hydraulic_sim(
    flowdir_raster,
    flowacc_raster,
    percent,
    zones_folder,
    dem_raster,
    width_raster,
    zbed_raster,
    manning_raster,
    mask_raster,
    output_folder,
    GIStools,
    messages=None,
):
    if GIStools is None:
        raise ValueError("A GIStools package must be provided.")

    if not os.path.isdir(zones_folder):
        raise ValueError(f"Tiles folder does not exist: {zones_folder}")
    if not os.path.isdir(output_folder):
        os.makedirs(output_folder)

    flowdir = GIStools.RasterAccess.FlowDirectionRaster(flowdir_raster)
    flowdir_grid = RasterGrid.from_raster_data(GIStools.RasterAccess.read_raster_grid(flowdir_raster))
    flowacc_grid = RasterGrid.from_raster_data(GIStools.RasterAccess.read_raster_grid(flowacc_raster))
    dem_grid = RasterGrid.from_raster_data(GIStools.RasterAccess.read_raster_grid(dem_raster))

    try:
        # Deliberate deviation from the legacy ArcGIS script: mismatched grids are
        # fatal because continuing would corrupt the flow-path sampling.
        flowdir_grid.check_match(flowacc_grid)
        flowdir_grid.check_match(dem_grid)
    except ValueError as exc:
        _add_error(messages, str(exc))

    vector_extension = _get_vector_extension(zones_folder, GIStools)
    polyzones = GIStools.DataManagement.open_vector_dataset(
        os.path.join(zones_folder, "polyzones" + vector_extension),
        layer_name="polyzones",
    )
    sourcepoints = GIStools.DataManagement.open_vector_dataset(
        os.path.join(zones_folder, "sourcepoints" + vector_extension),
        layer_name="sourcepoints",
    )
    spatial_reference = GIStools.DataManagement.get_spatial_reference(polyzones)

    zone_info = GIStools.DataManagement.read_feature_extents(polyzones, ["GRID_CODE", "Lake_ID"])
    zone_rasters = {}
    envelope_records = []
    for zone_row in zone_info["records"]:
        zone_id = int(zone_row["GRID_CODE"])
        extent = (
            float(zone_row["XMin"]),
            float(zone_row["YMin"]),
            float(zone_row["XMax"]),
            float(zone_row["YMax"]),
        )
        zone_raster_path = _zone_raster_path(zones_folder, zone_id)
        GIStools.Geoprocessing.clip_raster_to_extent(dem_raster, extent, zone_raster_path)
        zone_rasters[zone_id] = zone_raster_path
        envelope_records.append({
            "GRID_CODE": zone_id,
            "Lake_ID": _coerce_optional_int(zone_row.get("Lake_ID"), default=-999),
            "XMin": extent[0],
            "YMin": extent[1],
            "XMax": extent[2],
            "YMax": extent[3],
        })
    envelopezones_path = GIStools.DataManagement.write_hydraulic_envelopezones(
        zones_folder,
        envelope_records,
        spatial_reference=spatial_reference,
    )
    _add_message(messages, f"Saved envelope zones to {envelopezones_path}")

    source_info = GIStools.DataManagement.read_point_dataset(sourcepoints, ["ZoneID", "fpid"])
    input_points = []
    lateral_input_points = []
    output_points = []

    for source_row in source_info["records"]:
        zone_id = int(source_row["ZoneID"])
        zone_raster_path = zone_rasters.get(zone_id)
        if zone_raster_path in [None, ""]:
            _add_warning(messages, f"Skipping source point for missing zone raster: zone {zone_id}")
            continue

        main_point = _Point()
        main_point.type = "main"
        main_point.frompointid = _coerce_optional_int(source_row.get("fpid"), default=0)
        main_point.x = float(source_row["X"])
        main_point.y = float(source_row["Y"])
        main_point.numzone = zone_id
        main_point.side = None

        current_col = flowdir.x_to_col(main_point.x)
        current_row = flowdir.y_to_row(main_point.y)
        if not flowdir.in_bounds(current_row, current_col):
            _add_warning(
                messages,
                f"Source point fpid={main_point.frompointid} for zone {zone_id} is outside the flow direction raster",
            )
            continue

        current_flowacc = flowacc_grid.get_value(current_row, current_col)
        if current_flowacc is None:
            _add_error(
                messages,
                f"Source point fpid={main_point.frompointid} for zone {zone_id} is on a NoData flow accumulation cell.",
            )
        main_point.flowacc = float(current_flowacc)
        input_points.append(main_point)

        local_raster = RasterGrid.from_raster_data(GIStools.RasterAccess.read_raster_grid(zone_raster_path))
        local_col = local_raster.x_to_col(main_point.x)
        local_row = local_raster.y_to_row(main_point.y)
        last_flowacc = main_point.flowacc
        prev_row = current_row
        prev_col = current_col
        in_raster = True

        while in_raster:
            prev_row = current_row
            prev_col = current_col
            current_flowacc = flowacc_grid.get_value(current_row, current_col)
            if current_flowacc in [None, 0]:
                _add_error(
                    messages,
                    "Flow accumulation value of zero encountered. Check that source points are located on the flow network.",
                )

            if last_flowacc > 0 and 100.0 * float(current_flowacc - last_flowacc) / float(last_flowacc) >= float(percent):
                lateral_point = _Point()
                lateral_point.type = "lateral"
                lateral_point.frompointid = main_point.frompointid
                lateral_point.x = flowdir.col_to_x(current_col)
                lateral_point.y = flowdir.row_to_y(current_row)
                lateral_point.numzone = zone_id
                lateral_point.flowacc = float(current_flowacc)
                lateral_point.side = None
                lateral_input_points.append(lateral_point)
                last_flowacc = float(current_flowacc)

            next_step = flowdir.step(current_row, current_col)
            if next_step is None:
                in_raster = False
                continue

            next_row, next_col, _ = next_step
            local_row = local_row + (next_row - current_row)
            local_col = local_col + (next_col - current_col)
            current_row = next_row
            current_col = next_col

            if not flowdir.in_bounds(current_row, current_col):
                in_raster = False
            elif _get_direction(flowdir, current_row, current_col) not in VALID_D8_DIRECTIONS:
                in_raster = False

            if not local_raster.in_bounds(local_row, local_col):
                in_raster = False
            elif local_raster.get_value(local_row, local_col) is None:
                in_raster = False

        output_point = _Point()
        output_point.type = "exit"
        output_point.frompointid = main_point.frompointid
        output_point.numzone = zone_id
        output_point.x = flowdir.col_to_x(prev_col)
        output_point.y = flowdir.row_to_y(prev_row)
        output_point.flowacc = None
        output_point.side = _get_exit_side(output_point.x, output_point.y, local_raster)
        output_points.append(output_point)

    input_points.extend(lateral_input_points)

    inbci_path = GIStools.DataManagement.write_hydraulic_inbci(
        zones_folder,
        [_point_to_inbci_row(point) for point in input_points],
        spatial_reference=spatial_reference,
    )
    outbci_path = GIStools.DataManagement.write_hydraulic_outbci(
        zones_folder,
        [_point_to_outbci_row(point) for point in output_points],
        spatial_reference=spatial_reference,
    )
    _add_message(messages, f"Saved inbci to {inbci_path}")
    _add_message(messages, f"Saved outbci to {outbci_path}")

    points_by_zone = defaultdict(list)
    for point in input_points:
        points_by_zone[int(point.numzone)].append(point)

    for zone_id, zone_points in points_by_zone.items():
        sorted_points = sorted(zone_points, key=lambda item: item.flowacc)
        bci_path = os.path.join(output_folder, f"zone{zone_id}.bci")
        lateral_index = 0
        wrote_main = False
        with open(bci_path, "w") as handle:
            for point in sorted_points:
                if point.type == "main":
                    wrote_main = True
                    lateral_index = 0
                    handle.write(f"P\t{int(point.x)}\t{int(point.y)}\tQVAR\tzone{zone_id}\n")
                elif point.type == "lateral":
                    lateral_index += 1
                    handle.write(f"P\t{int(point.x)}\t{int(point.y)}\tQVAR\tzone{zone_id}_{lateral_index}\n")
        if not wrote_main:
            _add_error(messages, f"No main inflow point found for zone {zone_id}.")

        zone_raster_path = zone_rasters[zone_id]
        GIStools.Geoprocessing.raster_to_ascii(
            zone_raster_path,
            os.path.join(output_folder, f"zone{zone_id}.txt"),
        )

        raster_specs = [
            ("w", width_raster),
            ("d", zbed_raster),
            ("n", manning_raster),
            ("m", mask_raster),
        ]
        for prefix, raster in raster_specs:
            clipped_raster_path = os.path.join(zones_folder, f"{prefix}zone{zone_id}.tif")
            GIStools.Geoprocessing.clip_raster_to_template(raster, zone_raster_path, clipped_raster_path)
            GIStools.Geoprocessing.raster_to_ascii(
                clipped_raster_path,
                os.path.join(output_folder, f"{prefix}zone{zone_id}.txt"),
            )
            if os.path.exists(clipped_raster_path):
                os.remove(clipped_raster_path)

    _add_message(messages, "Hydraulic simulations preparation complete.")
    return {
        "envelopezones": envelopezones_path,
        "inbci": inbci_path,
        "outbci": outbci_path,
    }


def execute_DefBCI(
    flowdir_raster,
    flowacc_raster,
    percent,
    zones_folder,
    dem_raster,
    width_raster,
    zbed_raster,
    manning_raster,
    mask_raster,
    output_folder,
    messages=None,
    GIStools=None,
):
    return prepare_hydraulic_sim(
        flowdir_raster=flowdir_raster,
        flowacc_raster=flowacc_raster,
        percent=percent,
        zones_folder=zones_folder,
        dem_raster=dem_raster,
        width_raster=width_raster,
        zbed_raster=zbed_raster,
        manning_raster=manning_raster,
        mask_raster=mask_raster,
        output_folder=output_folder,
        GIStools=GIStools,
        messages=messages,
    )


def _get_vector_extension(zones_folder, GIStools):
    module_name = getattr(GIStools, "__name__", "").lower()
    preferred = ".gpkg" if "qgis" in module_name else ".shp"
    for extension in [preferred, ".shp", ".gpkg"]:
        if os.path.exists(os.path.join(zones_folder, "polyzones" + extension)):
            return extension
    return preferred


def _zone_raster_path(zones_folder, zone_id):
    return os.path.join(zones_folder, f"zone{int(zone_id)}.tif")


def _get_direction(flowdir, row_value, col_value):
    try:
        direction = int(flowdir.get_value(row_value, col_value))
    except (TypeError, ValueError):
        return None
    if direction not in VALID_D8_DIRECTIONS:
        return None
    return direction


def _get_exit_side(x_value, y_value, raster_grid):
    dist_w = float(x_value) - float(raster_grid.x_min)
    dist_e = float(raster_grid.x_max) - float(x_value)
    dist_s = float(y_value) - float(raster_grid.y_min)
    dist_n = float(raster_grid.y_max) - float(y_value)
    dist_side = min(dist_w, dist_e, dist_s, dist_n)

    if dist_side == dist_w:
        return "W"
    if dist_side == dist_e:
        return "E"
    if dist_side == dist_s:
        return "S"
    return "N"


def _coerce_optional_int(value, default):
    if value in [None, ""]:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _point_to_inbci_row(point):
    return {
        "zoneid": int(point.numzone),
        "flowacc": float(point.flowacc),
        "type": point.type,
        "fpid": int(point.frompointid),
        "X": float(point.x),
        "Y": float(point.y),
    }


def _point_to_outbci_row(point):
    return {
        "zoneid": int(point.numzone),
        "side": point.side,
        "X": float(point.x),
        "Y": float(point.y),
    }


def _add_message(messages, text):
    if messages is not None:
        messages.add_message(text)


def _add_warning(messages, text):
    if messages is not None:
        messages.add_warning(text)


def _add_error(messages, text):
    if messages is not None:
        messages.add_error(text)
    raise ValueError(text)
