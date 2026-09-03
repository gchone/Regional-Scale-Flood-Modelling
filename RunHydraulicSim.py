from __future__ import annotations

import math
import os
import shutil
import subprocess
from datetime import datetime

import numpy as np


MAX_DISTOUTPUT = 4000
SIMULATION_TIMEOUT = 7200
RETRY_TIMEOUT = 3600
MASS_BALANCE_TOLERANCE = 0.05
STEADY_TIME_THRESHOLD = 55000
RASTER_EXT = "tif"
_BASE_INBCI_FIELDS = ["zoneid", "flowacc", "type", "fpid"]


class pointflowpath:
    pass


class RasterGrid:
    def __init__(self, raster_data):
        self.array = np.asarray(raster_data["array"], dtype=float)
        if self.array.ndim != 2:
            raise ValueError("Raster arrays must be two-dimensional.")
        self.height, self.width = self.array.shape
        self.x_min = float(raster_data["x_min"])
        self.y_min = float(raster_data["y_min"])
        self.y_max = float(raster_data["y_max"])
        self.pixel_width = abs(float(raster_data["pixel_width"]))
        self.pixel_height = abs(float(raster_data["pixel_height"]))
        self.nodata = raster_data.get("nodata")
        self.raster_data = dict(raster_data)
        self.raster_data["array"] = self.array

    @property
    def x_max(self):
        return self.x_min + self.width * self.pixel_width

    def XtoCol(self, x_value):
        return int(math.floor((float(x_value) - self.x_min) / self.pixel_width))

    def YtoRow(self, y_value):
        return int(self.height - math.floor((float(y_value) - self.y_min) / self.pixel_height) - 1)

    def ColtoX(self, col_value):
        return self.x_min + (float(col_value) + 0.5) * self.pixel_width

    def RowtoY(self, row_value):
        return self.y_max - (float(row_value) + 0.5) * self.pixel_height

    def in_bounds(self, row_value, col_value):
        return 0 <= row_value < self.height and 0 <= col_value < self.width

    def getValue(self, row_value, col_value):
        if not self.in_bounds(row_value, col_value):
            return self.nodata
        value = self.array[row_value, col_value]
        if self.nodata is not None and _same_value(value, self.nodata):
            return self.nodata
        if isinstance(value, np.generic):
            return value.item()
        return value


def log_message(filelog, level, message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    filelog.write(f"[{timestamp}] [{level}] {message}\n")
    filelog.flush()


def check_mass_file(mass_file_path, lastdischarge, zonename, filelog, messages, tolerance=0.05):
    try:
        if not os.path.exists(mass_file_path):
            log_message(filelog, "WARNING", f"Mass file not found for {zonename}: {mass_file_path}")
            _add_warning(messages, f"[Mass Balance] Mass file not found for {zonename}: {mass_file_path}")
            return False

        try:
            with open(mass_file_path, "r") as filemass:
                lines = filemass.readlines()
        except IOError as exc:
            log_message(filelog, "ERROR", f"Cannot read mass file for {zonename}: {str(exc)}")
            _report_nonfatal_error(messages, f"[Mass Balance] Cannot read mass file for {zonename}: {str(exc)}")
            return False

        data_lines = [line for line in lines if line.strip() and not line.startswith("Time")]
        if not data_lines:
            log_message(filelog, "WARNING", f"No data found in mass file for {zonename}")
            _add_warning(messages, f"[Mass Balance] No data found in mass file for {zonename}")
            return False

        last_line = data_lines[-1].split()
        try:
            qin = float(last_line[6])
            qout = float(last_line[8])
        except (ValueError, IndexError) as exc:
            log_message(
                filelog,
                "ERROR",
                f"Cannot parse Qin/Qout from mass file for {zonename}. Expected at least 9 columns. Error: {str(exc)}",
            )
            _report_nonfatal_error(messages, f"[Mass Balance] Cannot parse Qin/Qout from mass file for {zonename}")
            return False

        all_checks_passed = True
        if qin != 0:
            qin_qout_diff = abs(qout - qin) / abs(qin)
        else:
            qin_qout_diff = abs(qout - qin)

        if qin_qout_diff > tolerance:
            all_checks_passed = False
            diff_pct = qin_qout_diff * 100
            msg = (
                f"Qin and Qout mismatch for {zonename}: Qin={qin:.3f} m³/s, Qout={qout:.3f} m³/s, "
                f"Difference={diff_pct:.2f}% (tolerance={tolerance * 100:.1f}%)"
            )
            log_message(filelog, "WARNING", msg)
            _add_warning(messages, f"[Mass Balance] {msg}")

        if lastdischarge != 0:
            qin_discharge_diff = abs(qin - lastdischarge) / abs(lastdischarge)
            qout_discharge_diff = abs(qout - lastdischarge) / abs(lastdischarge)
        else:
            qin_discharge_diff = abs(qin - lastdischarge)
            qout_discharge_diff = abs(qout - lastdischarge)
        del qout_discharge_diff

        if qin_discharge_diff > tolerance:
            all_checks_passed = False
            diff_pct = qin_discharge_diff * 100
            msg = (
                f"Qin does not match inbci discharge for {zonename}: Qin={qin:.3f} m³/s, "
                f"inbci discharge={lastdischarge:.3f} m³/s, Difference={diff_pct:.2f}% "
                f"(tolerance={tolerance * 100:.1f}%)"
            )
            log_message(filelog, "WARNING", msg)
            _add_warning(messages, f"[Mass Balance] {msg}")

        return all_checks_passed
    except Exception as exc:
        log_message(
            filelog,
            "ERROR",
            f"Unexpected exception in check_mass_file for {zonename}: {type(exc).__name__}: {str(exc)}",
        )
        _report_nonfatal_error(messages, f"[Mass Balance] Unexpected error for {zonename}: {str(exc)}")
        return False


def check_simulation_time(mass_file_path, zonename, filelog, messages):
    try:
        if not os.path.exists(mass_file_path):
            return False

        try:
            with open(mass_file_path, "r") as filemass:
                lines = filemass.readlines()
        except IOError as exc:
            log_message(filelog, "WARNING", f"Cannot read mass file for simulation time check: {str(exc)}")
            return False

        data_lines = [line for line in lines if line.strip() and not line.startswith("Time")]
        if not data_lines:
            return False

        last_line = data_lines[-1].split()
        try:
            time_value = float(last_line[0])
            if time_value <= 55000:
                log_message(
                    filelog,
                    "WARNING",
                    f"Simulation for {zonename} stopped before time 55000 (steady state not reached). "
                    f"Will retry without -steady flag.",
                )
                _add_warning(
                    messages,
                    f"[Simulation] Simulation for {zonename} stopped before time 55000. "
                    f"Retrying without steady state parameters.",
                )
                return True
        except (ValueError, IndexError) as exc:
            log_message(filelog, "WARNING", f"Cannot parse Time from mass file for {zonename}: {str(exc)}")
            return False

        return False
    except Exception as exc:
        log_message(
            filelog,
            "WARNING",
            f"Unexpected exception in check_simulation_time for {zonename}: {type(exc).__name__}: {str(exc)}",
        )
        return False


def execute_RunHydraulicSim(
    tiles_folder,
    simulations_folder,
    lisflood_folder,
    lakes,
    boundary_fields,
    output_velocity,
    simulation_time,
    cfl,
    channel_manning,
    zbed,
    discharge_fields=None,
    log_path=None,
    GIStools=None,
    messages=None,
    inbci=None,
    inbci_layers=None,
    downstream_boundary_raster=None,
):
    if GIStools is None:
        GIStools = _autodetect_gistools()
    if log_path in [None, ""]:
        raise ValueError("A log file path must be provided.")

    boundary_fields = _normalize_field_names(boundary_fields)
    scenarios = _build_discharge_scenarios(GIStools, tiles_folder, inbci, inbci_layers, discharge_fields)
    if len(boundary_fields) != len(scenarios):
        _add_error(messages, "Number of downstream boundary condition should match the number of input discharges")
    if downstream_boundary_raster not in [None, ""]:
        _add_warning(
            messages,
            "Optional downstream boundary raster is ignored to match ArcGIS-authoritative RunHydraulicSim behavior.",
        )

    lakes_source = _open_vector_dataset(GIStools, lakes)
    outbci_source = _load_tiles_vector_dataset(GIStools, tiles_folder, "outbci")
    envelopezones_source = _load_tiles_vector_dataset(GIStools, tiles_folder, "envelopezones")
    zbed_grid = RasterGrid(GIStools.RasterAccess.read_raster_grid(zbed))

    outbci_info = _read_point_dataset(GIStools, outbci_source, ["zoneid", "side"])
    outbci_by_zone = {}
    for row in outbci_info["records"]:
        outbci_by_zone[int(row["zoneid"])] = row

    envelope_info = _read_feature_extents(GIStools, envelopezones_source, ["GRID_CODE", "Lake_ID"])
    dict_outputwindow = {}
    lakeid_byzone = {}
    for zone_row in envelope_info["records"]:
        zone_id = int(zone_row["GRID_CODE"])
        lake_id = zone_row.get("Lake_ID")
        if lake_id not in [None, -999, "-999"]:
            lakeid_byzone[zone_id] = int(lake_id)
        perimeter = 2 * ((float(zone_row["XMax"]) - float(zone_row["XMin"])) + (float(zone_row["YMax"]) - float(zone_row["YMin"])))
        dict_outputwindow[zone_id] = min(MAX_DISTOUTPUT, perimeter / 4.0)

    lake_values_info = _read_table_dataset_with_oid(GIStools, lakes_source, boundary_fields)
    lake_values_by_id = {int(row["_oid"]): row for row in lake_values_info["records"]}

    result_paths = {}
    lisflood_exe = os.path.join(str(lisflood_folder), "lisflood.exe")
    os.makedirs(str(simulations_folder), exist_ok=True)

    with open(log_path, "w") as filelog:
        for scenario_index, scenario in enumerate(scenarios):
            fieldQ = scenario["field_name"]
            simname = scenario["name"]
            boundary_field = boundary_fields[scenario_index]
            currentsimfolder = os.path.join(str(simulations_folder), simname)
            currentresult = os.path.join(str(simulations_folder), f"res_{simname}.{RASTER_EXT}")

            skipsim = False
            if os.path.exists(currentresult):
                log_message(filelog, "INFO", f"Simulation result already exists for {simname}. Skipping simulation.")
                result_paths[simname] = currentresult
                continue

            os.makedirs(currentsimfolder, exist_ok=True)
            log_message(filelog, "INFO", f"Starting simulations with discharge field: {simname}")

            points_info = _read_point_dataset(GIStools, scenario["source"], _BASE_INBCI_FIELDS + [fieldQ])
            dictsegmentsin = {}
            for row in points_info["records"]:
                zone_id = int(row["zoneid"])
                dictsegmentsin.setdefault(zone_id, []).append(
                    {
                        "zoneid": zone_id,
                        "flowacc": float(row["flowacc"]),
                        "type": row["type"],
                        "fpid": int(row["fpid"]),
                        fieldQ: float(row[fieldQ]),
                    }
                )

            allzones = list(dictsegmentsin.keys())
            allzones.sort()

            dictzones_fp = {}
            for zone in allzones:
                fpid = dictsegmentsin[zone][0]["fpid"]
                if fpid not in dictzones_fp:
                    dictzones_fp[fpid] = []
                dictzones_fp[fpid].append(zone)

            sortedzones = []
            listfp = list(dictzones_fp.keys())
            listfp.sort()
            for fp in listfp:
                listzones_fp = dictzones_fp[fp]
                listzones_fp.sort(reverse=True)
                sortedzones.extend(listzones_fp)

            for zone in sortedzones:
                segment = dictsegmentsin[zone]
                for point in sorted(segment, key=lambda q_value: q_value["flowacc"]):
                    if point["type"] == "main" and not skipsim:
                        zonename = f"zone{zone}"
                        elev_zone_path = os.path.join(currentsimfolder, f"elev_{zonename}.{RASTER_EXT}")

                        tmp_result_path = None
                        try:
                            if not os.path.exists(elev_zone_path):
                                _add_message(messages, "Running simulation on zone " + str(zone))
                                distoutput = dict_outputwindow[zone]
                                ref_raster = RasterGrid(
                                    GIStools.RasterAccess.read_raster_grid(os.path.join(str(tiles_folder), f"{zonename}.{RASTER_EXT}"))
                                )

                                lakebci = False
                                hfix = None
                                res_downstream = None
                                if zone in lakeid_byzone:
                                    lake_record = lake_values_by_id.get(lakeid_byzone[zone])
                                    if lake_record is None:
                                        raise RuntimeError(f"Lake ID {lakeid_byzone[zone]} not found for tile #{zone}")
                                    hfix = _as_float(lake_record.get(boundary_field))
                                    if hfix is None:
                                        raise RuntimeError(f"Downsteam boudary condition not found for tile #{zone}")
                                    lakebci = True
                                else:
                                    if not os.path.exists(currentresult):
                                        raise RuntimeError("Downsteam boudary condition not found: tile #" + str(zone))
                                    tmp_result_path = os.path.join(currentsimfolder, f"tmp_{zonename}.{RASTER_EXT}")
                                    _remove_if_exists(tmp_result_path)
                                    shutil.copyfile(currentresult, tmp_result_path)
                                    res_downstream = RasterGrid(GIStools.RasterAccess.read_raster_grid(tmp_result_path))

                                outbci_point = outbci_by_zone.get(zone)
                                if outbci_point is None:
                                    raise RuntimeError(f"Missing outbci point for tile #{zone}")

                                sourcebci = os.path.join(str(simulations_folder), f"{zonename}.bci")
                                destinationbci = os.path.join(currentsimfolder, f"{zonename}.bci")
                                _prepare_bci_file(sourcebci, destinationbci)

                                newfilebdy = os.path.join(currentsimfolder, f"{zonename}.bdy")
                                lastdischarge = _write_bdy_file(
                                    newfilebdy,
                                    segment,
                                    zone,
                                    fieldQ,
                                    (ref_raster.pixel_height + ref_raster.pixel_width) / 2.0,
                                    int(simulation_time),
                                )

                                with open(destinationbci, "a") as filebci, open(newfilebdy, "a") as filebdy:
                                    _write_downstream_boundary(
                                        filebci,
                                        filebdy,
                                        ref_raster,
                                        res_downstream,
                                        lakebci,
                                        hfix,
                                        str(outbci_point["side"]),
                                        float(outbci_point["X"]),
                                        float(outbci_point["Y"]),
                                        distoutput,
                                        zbed_grid,
                                        int(simulation_time),
                                        1,
                                    )

                                _write_par_file(
                                    str(simulations_folder),
                                    simname,
                                    zone,
                                    int(simulation_time),
                                    float(channel_manning),
                                    bool(output_velocity),
                                    float(cfl),
                                )

                                try:
                                    steadytol = _compute_steadytol(lastdischarge)
                                except (ValueError, ZeroDivisionError) as exc:
                                    log_message(filelog, "ERROR", f"Cannot calculate steadytol for zone {zone}, sim {simname}: {str(exc)}")
                                    _report_nonfatal_error(messages, f"[LISFLOOD] Cannot calculate steadytol for zone {zone}")
                                    skipsim = True
                                    continue

                                log_message(filelog, "INFO", f"Starting LISFLOOD-FP simulation for zone {zone}, sim {simname} (steadytol={steadytol})")
                                try:
                                    result = _run_lisflood(
                                        lisflood_exe,
                                        os.path.join(str(simulations_folder), f"{zonename}.par"),
                                        str(simulations_folder),
                                        True,
                                        steadytol,
                                        SIMULATION_TIMEOUT,
                                    )
                                    if result.returncode != 0:
                                        log_message(
                                            filelog,
                                            "ERROR",
                                            f"LISFLOOD-FP failed for zone {zone}, sim {simname}. Return code: {result.returncode}",
                                        )
                                        if result.stderr:
                                            log_message(filelog, "ERROR", f"LISFLOOD stderr: {result.stderr[:500]}")
                                        _report_nonfatal_error(messages, f"[LISFLOOD] LISFLOOD-FP simulation failed for zone {zone}")
                                        skipsim = True
                                        continue
                                except subprocess.TimeoutExpired:
                                    log_message(filelog, "ERROR", f"LISFLOOD-FP timeout for zone {zone}, sim {simname} (> 1 hour)")
                                    _report_nonfatal_error(messages, f"[LISFLOOD] LISFLOOD-FP timeout for zone {zone}")
                                    skipsim = True
                                    continue
                                except Exception as exc:
                                    log_message(
                                        filelog,
                                        "ERROR",
                                        f"LISFLOOD-FP execution error for zone {zone}, sim {simname}: {type(exc).__name__}: {str(exc)}",
                                    )
                                    _report_nonfatal_error(messages, f"[LISFLOOD] LISFLOOD-FP execution error for zone {zone}: {str(exc)}")
                                    skipsim = True
                                    continue

                                log_message(filelog, "INFO", f"LISFLOOD-FP simulation completed for zone {zone}, sim {simname}")
                                mass_file_path = os.path.join(currentsimfolder, f"{zonename}.mass")

                                if check_simulation_time(mass_file_path, zonename, filelog, messages):
                                    log_message(filelog, "INFO", f"Retrying LISFLOOD-FP simulation for zone {zone} without -steady flag")
                                    output_files_to_remove = [
                                        os.path.join(currentsimfolder, f"{zonename}-0001.elev"),
                                        os.path.join(currentsimfolder, f"{zonename}-9999.elev"),
                                        os.path.join(currentsimfolder, f"{zonename}-0001.Vx"),
                                        os.path.join(currentsimfolder, f"{zonename}-9999.Vx"),
                                        os.path.join(currentsimfolder, f"{zonename}-0001.Vy"),
                                        os.path.join(currentsimfolder, f"{zonename}-9999.Vy"),
                                        mass_file_path,
                                    ]
                                    for output_file in output_files_to_remove:
                                        if os.path.exists(output_file):
                                            try:
                                                os.remove(output_file)
                                            except Exception as exc:
                                                log_message(filelog, "WARNING", f"Could not remove {output_file}: {str(exc)}")

                                    try:
                                        log_message(
                                            filelog,
                                            "INFO",
                                            f"Starting LISFLOOD-FP retry for zone {zone}, sim {simname} (without steady state parameters)",
                                        )
                                        result = _run_lisflood(
                                            lisflood_exe,
                                            os.path.join(str(simulations_folder), f"{zonename}.par"),
                                            str(simulations_folder),
                                            False,
                                            None,
                                            RETRY_TIMEOUT,
                                        )
                                        if result.returncode != 0:
                                            log_message(
                                                filelog,
                                                "ERROR",
                                                f"LISFLOOD-FP retry failed for zone {zone}, sim {simname}. Return code: {result.returncode}",
                                            )
                                            if result.stderr:
                                                log_message(filelog, "ERROR", f"LISFLOOD stderr: {result.stderr[:500]}")
                                            _report_nonfatal_error(messages, f"[LISFLOOD] LISFLOOD-FP retry simulation failed for zone {zone}")
                                            skipsim = True
                                            continue
                                        else:
                                            log_message(
                                                filelog,
                                                "INFO",
                                                f"LISFLOOD-FP retry simulation completed successfully for zone {zone}, sim {simname}",
                                            )
                                    except subprocess.TimeoutExpired:
                                        log_message(filelog, "ERROR", f"LISFLOOD-FP retry timeout for zone {zone}, sim {simname} (> 1 hour)")
                                        _report_nonfatal_error(messages, f"[LISFLOOD] LISFLOOD-FP retry timeout for zone {zone}")
                                        skipsim = True
                                        continue
                                    except Exception as exc:
                                        log_message(
                                            filelog,
                                            "ERROR",
                                            f"LISFLOOD-FP retry execution error for zone {zone}, sim {simname}: {type(exc).__name__}: {str(exc)}",
                                        )
                                        _report_nonfatal_error(messages, f"[LISFLOOD] LISFLOOD-FP retry execution error for zone {zone}: {str(exc)}")
                                        skipsim = True
                                        continue

                                try:
                                    check_mass_file(
                                        mass_file_path,
                                        lastdischarge,
                                        zonename,
                                        filelog,
                                        messages,
                                        MASS_BALANCE_TOLERANCE,
                                    )
                                except Exception as exc:
                                    log_message(
                                        filelog,
                                        "ERROR",
                                        f"Exception during mass balance validation for {zonename}: {type(exc).__name__}: {str(exc)}",
                                    )
                                    _report_nonfatal_error(messages, f"[Mass Balance] Exception during validation for {zonename}: {str(exc)}")

                                if tmp_result_path and os.path.exists(tmp_result_path):
                                    _remove_if_exists(tmp_result_path)

                                try:
                                    steady_state_reached = _collect_outputs(
                                        GIStools,
                                        currentsimfolder,
                                        zonename,
                                        bool(output_velocity),
                                        ref_raster.raster_data,
                                    )
                                    if not steady_state_reached:
                                        log_message(filelog, "WARNING", f"Steady state not reached for {zonename}, sim {simname} (using -0001.elev)")
                                        _add_warning(messages, f"[Simulation] Steady state not reached for {zonename}, sim {simname}")
                                except Exception as exc:
                                    log_message(
                                        filelog,
                                        "ERROR",
                                        f"Error during output file conversion for {zonename}: {type(exc).__name__}: {str(exc)}",
                                    )
                                    _report_nonfatal_error(messages, f"[Output] Error during file conversion for {zonename}")
                                    skipsim = True
                                    continue
                            else:
                                log_message(
                                    filelog,
                                    "INFO",
                                    f"Simulation skipped zone {zone}, results already exist (existing results merged)",
                                )
                                _add_message(messages, f"Simulation skipped zone {zone}, results already exist (existing results merged)")

                            try:
                                if not os.path.exists(currentresult):
                                    shutil.copyfile(elev_zone_path, currentresult)
                                else:
                                    mosaic_rasters_max(GIStools, currentresult, elev_zone_path, currentresult)
                            except BaseException as exc:
                                error_type = type(exc).__name__
                                error_msg = (
                                    f"CRITICAL ERROR in {simname}: simulation aborted during zone {zone}\n"
                                    f"Error Type: {error_type}\n"
                                    f"Error Message: {str(exc)}"
                                )
                                log_message(filelog, "ERROR", error_msg)
                                filelog.write(repr(exc) + "\n")
                                filelog.write("=" * 80 + "\n")
                                filelog.flush()
                                _report_nonfatal_error(messages, f"[Critical] {error_msg}")
                                _add_warning(messages, "Some simulations skipped. See log file for details.")
                                skipsim = True
                        except Exception as exc:
                            log_message(filelog, "ERROR", f"Sim aborted during zone {zone}, {simname}: {str(exc)}")
                            _add_warning(messages, f"Simulation for {simname} skipped from zone {zone} onward. See log file.")
                            skipsim = True
                        finally:
                            if tmp_result_path and os.path.exists(tmp_result_path):
                                _remove_if_exists(tmp_result_path)

            if os.path.exists(currentresult):
                result_paths[simname] = currentresult

        log_message(filelog, "INFO", "=" * 80)
        log_message(filelog, "INFO", "SIMULATION EXECUTION COMPLETED")
        log_message(filelog, "INFO", "=" * 80)

    return result_paths


def mosaic_rasters_max(GIStools, existing_path, new_path, output_path):
    existing_grid = GIStools.RasterAccess.read_raster_grid(existing_path)
    new_grid = GIStools.RasterAccess.read_raster_grid(new_path)
    merged_grid = _mosaic_grid_data_max(existing_grid, new_grid)
    GIStools.RasterAccess.write_raster_grid(merged_grid, merged_grid["array"], output_path, nodata=merged_grid["nodata"])
    return output_path


def _mosaic_grid_data_max(existing_grid, new_grid):
    px_w = float(existing_grid["pixel_width"])
    px_h = float(existing_grid["pixel_height"])
    xmin = min(float(existing_grid["x_min"]), float(new_grid["x_min"]))
    xmax = max(
        float(existing_grid["x_min"]) + int(existing_grid["width"]) * px_w,
        float(new_grid["x_min"]) + int(new_grid["width"]) * float(new_grid["pixel_width"]),
    )
    ymin = min(float(existing_grid["y_min"]), float(new_grid["y_min"]))
    ymax = max(float(existing_grid["y_max"]), float(new_grid["y_max"]))
    cols = int(round((xmax - xmin) / px_w))
    rows = int(round((ymax - ymin) / px_h))

    nodata = existing_grid.get("nodata")
    if nodata is None:
        nodata = new_grid.get("nodata")
    if nodata is None:
        nodata = -9999.0

    out_array = np.full((rows, cols), float(nodata), dtype=np.float32)
    _paste_grid_max(out_array, nodata, existing_grid, xmin, ymax, px_w, px_h)
    _paste_grid_max(out_array, nodata, new_grid, xmin, ymax, px_w, px_h)

    output_grid = dict(existing_grid)
    output_grid.update(
        {
            "array": out_array,
            "width": cols,
            "height": rows,
            "x_min": xmin,
            "y_min": ymin,
            "y_max": ymax,
            "pixel_width": px_w,
            "pixel_height": px_h,
            "nodata": nodata,
        }
    )
    return output_grid


def _paste_grid_max(out_array, out_nodata, source_grid, xmin, ymax, px_w, px_h):
    source_array = np.asarray(source_grid["array"], dtype=np.float32)
    source_nodata = source_grid.get("nodata")
    if source_nodata is not None:
        source_array = np.where(_same_value_array(source_array, source_nodata), np.float32(out_nodata), source_array)

    col_off = int(round((float(source_grid["x_min"]) - xmin) / px_w))
    row_off = int(round((ymax - float(source_grid["y_max"])) / px_h))
    sub_array = out_array[row_off:row_off + int(source_grid["height"]), col_off:col_off + int(source_grid["width"])]

    valid = ~_same_value_array(source_array, out_nodata)
    current_valid = ~_same_value_array(sub_array, out_nodata)
    both = valid & current_valid
    sub_array[both] = np.maximum(sub_array[both], source_array[both])
    only_new = valid & ~current_valid
    sub_array[only_new] = source_array[only_new]


def _prepare_bci_file(source_bci, destination_bci):
    if os.path.isfile(destination_bci):
        os.remove(destination_bci)
    shutil.copy(source_bci, destination_bci)
    with open(destination_bci, "r") as sourcefile:
        lines = sourcefile.readlines()
    with open(destination_bci, "w") as destinationfile:
        for line in lines:
            if line.strip() and line[0] == "P":
                destinationfile.write(line)


def _write_bdy_file(bdy_path, segment, zone, field_name, cellsize, sim_time):
    lastdischarge = None
    latnum = 0
    zonename = "zone" + str(zone)

    with open(bdy_path, "w") as filebdy:
        for point in sorted(segment, key=lambda q_value: q_value["flowacc"]):
            q_value = float(point[field_name])
            if point["type"] == "main":
                pointdischarge = q_value / cellsize
                lastdischarge = q_value
                filebdy.write(zonename + ".bdy\n")
                filebdy.write(zonename + "\n")
                filebdy.write("3\tseconds\n")
                filebdy.write("0\t0\n")
                filebdy.write("{0:.3f}".format(pointdischarge) + "\t50000\n")
                filebdy.write("{0:.3f}".format(pointdischarge) + "\t" + str(sim_time))
            else:
                latnum += 1
                pointdischarge = (q_value - lastdischarge) / cellsize
                lastdischarge = q_value
                filebdy.write("\n" + zonename + "_" + str(latnum) + "\n")
                filebdy.write("3\tseconds\n")
                filebdy.write("0\t0\n")
                filebdy.write("{0:.3f}".format(pointdischarge) + "\t50000\n")
                filebdy.write("{0:.3f}".format(pointdischarge) + "\t" + str(sim_time))

    if lastdischarge is None:
        raise RuntimeError(f"No main inflow point found for {zonename}")
    return lastdischarge


def _write_hvar(filebci, filebdy, side, lim_a, lim_b, zdep, hfix, simtime, numhvar):
    filebci.write(side + "\t" + "{0:.2f}".format(lim_a) + "\t" + "{0:.2f}".format(lim_b) + "\tHVAR\thvar" + str(numhvar) + "\n")
    filebdy.write("\nhvar" + str(numhvar) + "\n")
    filebdy.write("4\tseconds\n")
    filebdy.write("{0:.2f}".format(zdep) + "\t0\n")
    filebdy.write("{0:.2f}".format(zdep) + "\t50000\n")
    filebdy.write("{0:.2f}".format(hfix) + "\t55000\n")
    filebdy.write("{0:.2f}".format(hfix) + "\t" + str(simtime))
    return numhvar + 1


def _write_downstream_boundary(
    filebci,
    filebdy,
    ref_raster,
    res_downstream,
    lakebci,
    hfix,
    side,
    point_x,
    point_y,
    distoutput,
    zbed,
    simtime,
    numhvar,
):
    newpoint = pointflowpath()
    newpoint.side = side
    newpoint.x = point_x
    newpoint.y = point_y
    colinc = 0
    rowinc = 0
    distinc = 0
    newpoint.side2 = "0"
    newpoint.lim3 = 0
    newpoint.lim4 = 0

    currentcol = ref_raster.XtoCol(newpoint.x)
    currentrow = ref_raster.YtoRow(newpoint.y)
    if newpoint.side == "W" or newpoint.side == "E":
        rowinc = 1
        distinc = ref_raster.pixel_height
        newpoint.lim1 = newpoint.y - distinc / 2.0
    else:
        colinc = 1
        distinc = ref_raster.pixel_width
        newpoint.lim1 = newpoint.x + distinc / 2.0
    distance = 0

    if not lakebci:
        hresult_row = ref_raster.YtoRow(newpoint.y)
        hresult_col = ref_raster.XtoCol(newpoint.x)
        if newpoint.side == "W":
            hresult_col -= 1
        elif newpoint.side == "E":
            hresult_col += 1
        elif newpoint.side == "N":
            hresult_row -= 1
        elif newpoint.side == "S":
            hresult_row += 1
        res_downstream_row = res_downstream.YtoRow(ref_raster.RowtoY(hresult_row))
        res_downstream_col = res_downstream.XtoCol(ref_raster.ColtoX(hresult_col))
        hfix = res_downstream.getValue(res_downstream_row, res_downstream_col)
        if hfix != res_downstream.nodata:
            if newpoint.side == "N" or newpoint.side == "S":
                lim_a = newpoint.x + distinc / 2.0
                lim_b = newpoint.x - distinc / 2.0
            else:
                lim_a = newpoint.y + distinc / 2.0
                lim_b = newpoint.y - distinc / 2.0
            zdep = min(zbed.getValue(zbed.YtoRow(newpoint.y), zbed.XtoCol(newpoint.x)) + 0.3, hfix)
            numhvar = _write_hvar(filebci, filebdy, newpoint.side, lim_a, lim_b, zdep, hfix, simtime, numhvar)

    while not (currentcol < 0 or currentcol >= ref_raster.width or currentrow < 0 or currentrow >= ref_raster.height) and distance < distoutput / 2.0:
        distance += distinc
        currentrow += rowinc
        currentcol += colinc
        if newpoint.side == "W" or newpoint.side == "E":
            newpoint.lim1 = ref_raster.RowtoY(currentrow)
        else:
            newpoint.lim1 = ref_raster.ColtoX(currentcol)
        if not lakebci:
            hresult_row = res_downstream.YtoRow(ref_raster.RowtoY(currentrow))
            hresult_col = res_downstream.XtoCol(ref_raster.ColtoX(currentcol))
            if newpoint.side == "W":
                hresult_col -= 1
            elif newpoint.side == "E":
                hresult_col += 1
            elif newpoint.side == "N":
                hresult_row -= 1
            elif newpoint.side == "S":
                hresult_row += 1
            hfix = res_downstream.getValue(hresult_row, hresult_col)
            if hfix != res_downstream.nodata:
                zdep = min(ref_raster.getValue(currentrow, currentcol) + 0.3, hfix)
                numhvar = _write_hvar(
                    filebci,
                    filebdy,
                    newpoint.side,
                    newpoint.lim1 + distinc / 2.0,
                    newpoint.lim1 - distinc / 2.0,
                    zdep,
                    hfix,
                    simtime,
                    numhvar,
                )
    currentrow -= rowinc
    currentcol -= colinc

    if distance < distoutput / 2.0:
        distance -= distinc
        if newpoint.side == "W":
            colinc = 1
            rowinc = 0
            distinc = ref_raster.pixel_width
            newpoint.lim3 = ref_raster.x_min + (currentcol + 0.5) * ref_raster.pixel_width
            newpoint.side2 = "S"
        elif newpoint.side == "E":
            colinc = -1
            rowinc = 0
            distinc = ref_raster.pixel_width
            newpoint.lim3 = ref_raster.x_min + (currentcol + 0.5) * ref_raster.pixel_width
            newpoint.side2 = "S"
        elif newpoint.side == "N":
            rowinc = 1
            colinc = 0
            distinc = ref_raster.pixel_height
            newpoint.lim3 = max(ref_raster.y_min, ref_raster.y_max - (currentrow + 1) * ref_raster.pixel_height) + 0.5 * ref_raster.pixel_height
            newpoint.side2 = "E"
        elif newpoint.side == "S":
            rowinc = -1
            colinc = 0
            distinc = ref_raster.pixel_height
            newpoint.lim3 = max(ref_raster.y_min, ref_raster.y_max - (currentrow + 1) * ref_raster.pixel_height) + 0.5 * ref_raster.pixel_height
            newpoint.side2 = "E"
        while (
            not (currentcol < 0 or currentcol >= ref_raster.width or currentrow < 0 or currentrow >= ref_raster.height)
            and ref_raster.getValue(currentrow, currentcol) != ref_raster.nodata
            and distance < distoutput / 2.0
        ):
            distance += distinc
            currentrow += rowinc
            currentcol += colinc
            if newpoint.side2 == "W" or newpoint.side2 == "E":
                newpoint.lim4 = ref_raster.RowtoY(currentrow)
            else:
                newpoint.lim4 = ref_raster.ColtoX(currentcol)
            if not lakebci:
                hresult_row = res_downstream.YtoRow(ref_raster.RowtoY(currentrow))
                hresult_col = res_downstream.XtoCol(ref_raster.ColtoX(currentcol))
                if newpoint.side == "W":
                    hresult_col -= 1
                elif newpoint.side == "E":
                    hresult_col += 1
                elif newpoint.side == "N":
                    hresult_row -= 1
                elif newpoint.side == "S":
                    hresult_row += 1
                hfix = res_downstream.getValue(hresult_row, hresult_col)
                if hfix != res_downstream.nodata:
                    zdep = min(ref_raster.getValue(currentrow, currentcol) + 0.3, hfix)
                    numhvar = _write_hvar(
                        filebci,
                        filebdy,
                        newpoint.side2,
                        newpoint.lim4 + distinc / 2.0,
                        newpoint.lim4 - distinc / 2.0,
                        zdep,
                        hfix,
                        simtime,
                        numhvar,
                    )
        currentrow -= rowinc
        currentcol -= colinc
        if lakebci:
            filebci.write(
                newpoint.side2 + "\t" + "{0:.2f}".format(newpoint.lim3) + "\t" + "{0:.2f}".format(newpoint.lim4) + "\tHVAR\thvar" + "\n"
            )

    colinc = 0
    rowinc = 0
    distinc = 0
    if newpoint.side == "W" or newpoint.side == "E":
        rowinc = -1
        distinc = ref_raster.pixel_height
        newpoint.lim2 = newpoint.y + distinc / 2.0
    else:
        colinc = -1
        distinc = ref_raster.pixel_width
        newpoint.lim2 = newpoint.x - distinc / 2.0
    currentcol = ref_raster.XtoCol(newpoint.x)
    currentrow = ref_raster.YtoRow(newpoint.y)
    distance = 0
    while (
        not (currentcol < 0 or currentcol >= ref_raster.width or currentrow < 0 or currentrow >= ref_raster.height)
        and ref_raster.getValue(currentrow, currentcol) != ref_raster.nodata
        and distance < distoutput / 2.0
    ):
        distance += distinc
        currentrow += rowinc
        currentcol += colinc
        if newpoint.side == "W" or newpoint.side == "E":
            newpoint.lim2 = ref_raster.RowtoY(currentrow)
        else:
            newpoint.lim2 = ref_raster.ColtoX(currentcol)
        if not lakebci:
            hresult_row = res_downstream.YtoRow(ref_raster.RowtoY(currentrow))
            hresult_col = res_downstream.XtoCol(ref_raster.ColtoX(currentcol))
            if newpoint.side == "W":
                hresult_col -= 1
            elif newpoint.side == "E":
                hresult_col += 1
            elif newpoint.side == "N":
                hresult_row -= 1
            elif newpoint.side == "S":
                hresult_row += 1
            hfix = res_downstream.getValue(hresult_row, hresult_col)
            if hfix != res_downstream.nodata:
                zdep = min(ref_raster.getValue(currentrow, currentcol) + 0.3, hfix)
                numhvar = _write_hvar(
                    filebci,
                    filebdy,
                    newpoint.side,
                    newpoint.lim2 + distinc / 2.0,
                    newpoint.lim2 - distinc / 2.0,
                    zdep,
                    hfix,
                    simtime,
                    numhvar,
                )
    currentrow -= rowinc
    currentcol -= colinc

    if distance < distoutput / 2.0:
        distance -= distinc
        if newpoint.side == "W":
            colinc = 1
            rowinc = 0
            distinc = ref_raster.pixel_width
            newpoint.lim3 = ref_raster.x_min + (currentcol + 0.5) * ref_raster.pixel_width
            newpoint.side2 = "N"
        elif newpoint.side == "E":
            colinc = -1
            rowinc = 0
            distinc = ref_raster.pixel_width
            newpoint.lim3 = ref_raster.x_min + (currentcol + 0.5) * ref_raster.pixel_width
            newpoint.side2 = "N"
        elif newpoint.side == "N":
            rowinc = 1
            colinc = 0
            distinc = ref_raster.pixel_height
            newpoint.lim3 = max(ref_raster.y_min, ref_raster.y_max - (currentrow + 1) * ref_raster.pixel_height) + 0.5 * ref_raster.pixel_height
            newpoint.side2 = "W"
        elif newpoint.side == "S":
            rowinc = -1
            colinc = 0
            distinc = ref_raster.pixel_height
            newpoint.lim3 = max(ref_raster.y_min, ref_raster.y_max - (currentrow + 1) * ref_raster.pixel_height) + 0.5 * ref_raster.pixel_height
            newpoint.side2 = "W"
        while (
            not (currentcol < 0 or currentcol >= ref_raster.width or currentrow < 0 or currentrow >= ref_raster.height)
            and ref_raster.getValue(currentrow, currentcol) != ref_raster.nodata
            and distance < distoutput / 2.0
        ):
            distance += distinc
            currentrow += rowinc
            currentcol += colinc
            if newpoint.side2 == "W" or newpoint.side2 == "E":
                newpoint.lim4 = ref_raster.RowtoY(currentrow)
            else:
                newpoint.lim4 = ref_raster.ColtoX(currentcol)
            if not lakebci:
                hresult_row = res_downstream.YtoRow(ref_raster.RowtoY(currentrow))
                hresult_col = res_downstream.XtoCol(ref_raster.ColtoX(currentcol))
                if newpoint.side == "W":
                    hresult_col -= 1
                elif newpoint.side == "E":
                    hresult_col += 1
                elif newpoint.side == "N":
                    hresult_row -= 1
                elif newpoint.side == "S":
                    hresult_row += 1
                hfix = res_downstream.getValue(hresult_row, hresult_col)
                if hfix != res_downstream.nodata:
                    zdep = min(ref_raster.getValue(currentrow, currentcol) + 0.3, hfix)
                    numhvar = _write_hvar(
                        filebci,
                        filebdy,
                        newpoint.side2,
                        newpoint.lim4 + distinc / 2.0,
                        newpoint.lim4 - distinc / 2.0,
                        zdep,
                        hfix,
                        simtime,
                        numhvar,
                    )
        currentrow -= rowinc
        currentcol -= colinc
        if lakebci:
            filebci.write(
                newpoint.side2 + "\t" + "{0:.2f}".format(newpoint.lim3) + "\t" + "{0:.2f}".format(newpoint.lim4) + "\tHVAR\thvar" + "\n"
            )

    if lakebci:
        filebci.write(
            newpoint.side + "\t" + "{0:.2f}".format(newpoint.lim1) + "\t" + "{0:.2f}".format(newpoint.lim2) + "\tHVAR\thvar" + "\n"
        )
        zdep = min(zbed.getValue(zbed.YtoRow(newpoint.y), zbed.XtoCol(newpoint.x)) + 0.3, hfix)
        filebdy.write("\nhvar\n")
        filebdy.write("4\tseconds\n")
        filebdy.write("{0:.2f}".format(zdep) + "\t0\n")
        filebdy.write("{0:.2f}".format(zdep) + "\t50000\n")
        filebdy.write("{0:.2f}".format(hfix) + "\t55000\n")
        filebdy.write("{0:.2f}".format(hfix) + "\t" + str(simtime))
        numhvar += 1

    return numhvar


def _write_par_file(sim_folder, simname, zone, sim_time, channel_manning, voutput, cfl):
    zonename = "zone" + str(zone)
    newfile = os.path.join(sim_folder, zonename + ".par")
    if os.path.isfile(newfile):
        os.remove(newfile)

    with open(newfile, "w") as filepar:
        filepar.write("DEMfile\t" + zonename + ".txt\n")
        filepar.write("resroot\t" + zonename + "\n")
        filepar.write("dirroot\t" + simname + "\n")
        filepar.write("manningfile\tn" + zonename + ".txt\n")
        filepar.write("bcifile\t" + simname + "\\" + zonename + ".bci\n")
        filepar.write("sim_time\t" + str(sim_time) + "\n")
        filepar.write("saveint\t" + str(sim_time) + "\n")
        filepar.write("bdyfile\t" + simname + "\\" + zonename + ".bdy\n")
        filepar.write("SGCwidth\tw" + zonename + ".txt\n")
        filepar.write("SGCbank\t" + zonename + ".txt\n")
        filepar.write("SGCbed\td" + zonename + ".txt\n")
        filepar.write("SGCn\t" + str(channel_manning) + "\n")
        filepar.write("chanmask\tm" + zonename + ".txt\n")
        if voutput:
            filepar.write("hazard\n")
            filepar.write("qoutput\n")
        filepar.write("cfl\t" + str(cfl) + "\n")
        filepar.write("max_Froude\t1\n")


def _compute_steadytol(lastdischarge):
    return str(round(lastdischarge / 200.0, -int(math.floor(math.log10(abs(lastdischarge / 200.0))))))


def _run_lisflood(lisflood_exe, par_path, sim_folder, steady, steadytol, timeout):
    command = [lisflood_exe]
    if steady:
        command.extend(["-steady", "-steadytol", steadytol])
    command.append(par_path)
    return subprocess.run(command, shell=True, cwd=sim_folder, capture_output=True, text=True, timeout=timeout)


def _collect_outputs(GIStools, currentsimfolder, zonename, voutput, reference_raster_data):
    elev_text = os.path.join(currentsimfolder, zonename + "elev.txt")
    _remove_if_exists(elev_text)

    steady_elev = os.path.join(currentsimfolder, zonename + "-9999.elev")
    if os.path.exists(steady_elev):
        os.rename(steady_elev, elev_text)
        steady_state_reached = True
    else:
        final_elev = os.path.join(currentsimfolder, zonename + "-0001.elev")
        if not os.path.exists(final_elev):
            raise RuntimeError(f"No elevation output file found for {zonename}")
        os.rename(final_elev, elev_text)
        steady_state_reached = False

    if voutput and (
        os.path.exists(os.path.join(currentsimfolder, zonename + "-9999.Vx"))
        or os.path.exists(os.path.join(currentsimfolder, zonename + "-0001.Vx"))
    ):
        vx_text = os.path.join(currentsimfolder, zonename + "Vx.txt")
        vy_text = os.path.join(currentsimfolder, zonename + "Vy.txt")
        _remove_if_exists(vx_text)
        _remove_if_exists(vy_text)

        if os.path.exists(os.path.join(currentsimfolder, zonename + "-9999.Vx")):
            os.rename(os.path.join(currentsimfolder, zonename + "-9999.Vx"), vx_text)
            os.rename(os.path.join(currentsimfolder, zonename + "-9999.Vy"), vy_text)
        else:
            os.rename(os.path.join(currentsimfolder, zonename + "-0001.Vx"), vx_text)
            os.rename(os.path.join(currentsimfolder, zonename + "-0001.Vy"), vy_text)

        _ascii_to_raster(GIStools, vx_text, os.path.join(currentsimfolder, "Vx_" + zonename + "." + RASTER_EXT), reference_raster_data)
        _ascii_to_raster(GIStools, vy_text, os.path.join(currentsimfolder, "Vy_" + zonename + "." + RASTER_EXT), reference_raster_data)

    _ascii_to_raster(
        GIStools,
        elev_text,
        os.path.join(currentsimfolder, "elev_" + zonename + "." + RASTER_EXT),
        reference_raster_data,
    )
    return steady_state_reached


def _ascii_to_raster(GIStools, ascii_path, output_path, reference_raster_data):
    ascii_grid = _read_ascii_grid(ascii_path)
    raster_data = dict(reference_raster_data)
    raster_data.update(ascii_grid)
    raster_data["array"] = ascii_grid["array"]
    GIStools.RasterAccess.write_raster_grid(raster_data, raster_data["array"], output_path, nodata=raster_data["nodata"])
    return output_path


def _read_ascii_grid(ascii_path):
    header_values = {}
    data_lines = []
    with open(ascii_path, "r") as fileascii:
        for line in fileascii:
            stripped = line.strip()
            if stripped == "":
                continue
            parts = stripped.split()
            key = parts[0].lower()
            if key in ["ncols", "nrows", "xllcorner", "yllcorner", "xllcenter", "yllcenter", "cellsize", "nodata_value"]:
                header_values[key] = float(parts[1]) if key not in ["ncols", "nrows"] else int(parts[1])
            else:
                data_lines.append(stripped)

    ncols = int(header_values["ncols"])
    nrows = int(header_values["nrows"])
    cellsize = float(header_values["cellsize"])
    nodata = header_values.get("nodata_value", -9999.0)

    if "xllcorner" in header_values:
        x_min = float(header_values["xllcorner"])
    else:
        x_min = float(header_values["xllcenter"]) - cellsize / 2.0
    if "yllcorner" in header_values:
        y_min = float(header_values["yllcorner"])
    else:
        y_min = float(header_values["yllcenter"]) - cellsize / 2.0

    array = np.loadtxt(data_lines, dtype=np.float32)
    array = np.atleast_2d(array)
    if array.shape != (nrows, ncols):
        array = array.reshape((nrows, ncols))

    return {
        "array": array,
        "width": ncols,
        "height": nrows,
        "x_min": x_min,
        "y_min": y_min,
        "y_max": y_min + nrows * cellsize,
        "pixel_width": cellsize,
        "pixel_height": cellsize,
        "nodata": nodata,
    }


def _build_discharge_scenarios(GIStools, tiles_folder, inbci, inbci_layers, discharge_fields):
    normalized_fields = _normalize_field_names(discharge_fields)
    if inbci_layers not in [None, ""]:
        scenarios = []
        layers = list(inbci_layers)
        if normalized_fields and len(normalized_fields) != len(layers):
            raise ValueError("If discharge_fields are provided with inbci_layers, both lists must have the same length.")
        for index, layer in enumerate(layers):
            field_name = normalized_fields[index] if normalized_fields else _infer_discharge_field_name(GIStools, layer)
            scenarios.append({"name": str(field_name), "field_name": str(field_name), "source": layer})
        _check_duplicate_scenario_names(scenarios)
        return scenarios

    if inbci in [None, ""]:
        inbci = _load_tiles_vector_dataset(GIStools, tiles_folder, "inbci")

    if not normalized_fields:
        raise ValueError("At least one discharge field must be provided.")

    source = inbci
    scenarios = [{"name": str(field_name), "field_name": str(field_name), "source": source} for field_name in normalized_fields]
    _check_duplicate_scenario_names(scenarios)
    return scenarios


def _check_duplicate_scenario_names(scenarios):
    seen_names = set()
    for scenario in scenarios:
        scenario_name = str(scenario["name"]).lower()
        if scenario_name in seen_names:
            raise ValueError(f"Duplicate discharge name '{scenario['name']}' provided.")
        seen_names.add(scenario_name)


def _infer_discharge_field_name(GIStools, source):
    points_info = _read_point_dataset(GIStools, source, None)
    available_fields = points_info["field_names"]
    source_name = _get_source_name(source)
    if str(source_name).lower().startswith("inbci_"):
        candidate_name = str(source_name)[len("inbci_"):]
        for field_name in available_fields:
            if str(field_name).lower() == candidate_name.lower():
                return field_name

    base_field_names = {field_name.lower() for field_name in _BASE_INBCI_FIELDS}
    extra_fields = [field_name for field_name in available_fields if str(field_name).lower() not in base_field_names]
    if len(extra_fields) == 1:
        return extra_fields[0]

    raise ValueError(
        f"Could not infer the discharge field for '{source_name}'. "
        f"Expected a layer named inbci_<field> or exactly one extra field beyond {_BASE_INBCI_FIELDS}."
    )


def _load_tiles_vector_dataset(GIStools, tiles_folder, basename):
    source_path, layer_name = _resolve_tiles_vector_path(str(tiles_folder), basename)
    return _open_vector_dataset(GIStools, source_path, layer_name)


def _resolve_tiles_vector_path(tiles_folder, basename):
    shapefile_path = os.path.join(tiles_folder, basename + ".shp")
    if os.path.exists(shapefile_path):
        return shapefile_path, None
    geopackage_path = os.path.join(tiles_folder, basename + ".gpkg")
    if os.path.exists(geopackage_path):
        return geopackage_path, basename
    raise ValueError(f"Could not find '{basename}.shp' or '{basename}.gpkg' in '{tiles_folder}'.")


def _open_vector_dataset(GIStools, source, layer_name=None):
    opener = getattr(GIStools.DataManagement, "open_vector_dataset", None)
    if opener is None:
        return source
    return opener(source, layer_name)


def _read_point_dataset(GIStools, source, field_names=None):
    reader = getattr(GIStools.DataManagement, "read_point_dataset_any", None)
    if reader is None:
        reader = GIStools.DataManagement.read_point_dataset
    return reader(source, field_names)


def _read_table_dataset_with_oid(GIStools, source, field_names=None):
    reader = getattr(GIStools.DataManagement, "read_table_dataset_with_oid", None)
    if reader is None:
        raise ValueError("GIStools.DataManagement.read_table_dataset_with_oid is required.")
    return reader(source, field_names)


def _read_feature_extents(GIStools, source, field_names=None):
    reader = getattr(GIStools.DataManagement, "read_feature_extents", None)
    if reader is None:
        raise ValueError("GIStools.DataManagement.read_feature_extents is required.")
    return reader(source, field_names)


def _remove_if_exists(path):
    if os.path.exists(path):
        os.remove(path)


def _normalize_field_names(field_names):
    if field_names in [None, ""]:
        return []
    if isinstance(field_names, str):
        values = field_names.split(";")
    else:
        values = list(field_names)
    normalized = []
    for value in values:
        if value in [None, ""]:
            continue
        cleaned = str(value).strip()
        if cleaned not in [None, ""]:
            normalized.append(cleaned)
    return normalized


def _same_value(value_a, value_b):
    try:
        return np.float32(value_a) == np.float32(value_b)
    except Exception:
        return value_a == value_b


def _same_value_array(array_values, nodata_value):
    return np.isclose(array_values.astype(np.float32), np.float32(nodata_value), equal_nan=True)


def _as_float(value):
    if value in [None, ""]:
        return None
    if hasattr(value, "isNull"):
        try:
            if value.isNull():
                return None
        except Exception:
            pass
    try:
        float_value = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(float_value):
        return None
    return float_value


def _get_source_name(source):
    if hasattr(source, "name"):
        try:
            return source.name()
        except Exception:
            pass
    return str(source)


def _add_message(messages, message):
    if messages is None:
        return
    if hasattr(messages, "add_message"):
        messages.add_message(message)
        return
    manager = getattr(messages, "manager", None)
    if manager is not None and hasattr(manager, "addMessage"):
        manager.addMessage(message)
        return
    feedback = getattr(messages, "feedback", None)
    if feedback is not None and hasattr(feedback, "pushInfo"):
        feedback.pushInfo(message)


def _add_warning(messages, message):
    if messages is None:
        return
    if hasattr(messages, "add_warning"):
        messages.add_warning(message)
        return
    manager = getattr(messages, "manager", None)
    if manager is not None and hasattr(manager, "addWarningMessage"):
        manager.addWarningMessage(message)
        return
    feedback = getattr(messages, "feedback", None)
    if feedback is not None and hasattr(feedback, "pushWarning"):
        feedback.pushWarning(message)


def _report_nonfatal_error(messages, message):
    if messages is None:
        return
    manager = getattr(messages, "manager", None)
    if manager is not None and hasattr(manager, "addErrorMessage"):
        manager.addErrorMessage(message)
        return
    feedback = getattr(messages, "feedback", None)
    if feedback is not None:
        if hasattr(feedback, "reportError"):
            try:
                feedback.reportError(message, False)
            except TypeError:
                feedback.reportError(message)
            return
        if hasattr(feedback, "pushWarning"):
            feedback.pushWarning("[ERROR] " + message)
            return
    _add_warning(messages, "[ERROR] " + message)


def _add_error(messages, message):
    if messages is not None and hasattr(messages, "add_error"):
        messages.add_error(message)
    raise RuntimeError(message)


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
