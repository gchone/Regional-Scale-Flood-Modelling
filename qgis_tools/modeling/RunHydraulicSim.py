import math
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from osgeo import gdal

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessing,
    QgsProcessingParameterFile,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterField,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterNumber,
    QgsProcessingParameterFileDestination,
    QgsVectorLayer,
    QgsWkbTypes,
)

sys.path.append(str(Path(__file__).resolve().parents[0]))

gdal.UseExceptions()

# Confirmed against the Tiles folder listing: HydraulicSimPrep.py writes
# per-zone rasters as GeoTIFF.
RASTER_EXT = "tif"

# Max size of the downstream boundary output window (m). Effective size is
# reduced to 1/4 of the zone's perimeter if that's smaller. Was a
# user-supplied HydraulicSimPrep parameter (DISTOUTPUT) before the exit
# window moved to run time (ArcGIS_dev) - now computed here instead.
MAX_DISTOUTPUT = 4000

# Maximum time (s) allowed for a single LISFLOOD-FP tile simulation before
# aborting that zone.
SIM_TIMEOUT = 7200

# Tolerance for the Qin/Qout and Qin-vs-inbci-discharge mass balance checks.
MASS_BALANCE_TOLERANCE = 0.05

# A simulation that stopped at or before this time is treated as "steady
# state not reached" and retried once without -steady/-steadytol.
STEADY_TIME_THRESHOLD = 55000


class RunHydraulicSimulations(QgsProcessingAlgorithm):

    TILES_FOLDER    = "TILES_FOLDER"
    INBCI_LAYERS    = "INBCI_LAYERS"
    SIM_FOLDER      = "SIM_FOLDER"
    LISFLOOD_FOLDER = "LISFLOOD_FOLDER"
    VOUTPUT         = "VOUTPUT"
    LAKES           = "LAKES"
    LAKES_RASTER    = "LAKES_RASTER"
    ZFIELDS         = "ZFIELDS"
    CHANNEL_MANNING = "CHANNEL_MANNING"
    SIM_TIME        = "SIM_TIME"
    CFL             = "CFL"
    ZBED            = "ZBED"
    LOG             = "LOG"

    def name(self):
        return "run_hydraulic_simulations"

    def displayName(self):
        return "Run hydraulic simulations with LISFLOOD-FP"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Modeling"

    def groupId(self):
        return "concordiariverlab_floodtools_modeling"

    def createInstance(self):
        return RunHydraulicSimulations()

    def shortHelpString(self):
        return (
            "Run hydraulic simulations with LISFLOOD-FP\n\n"
            "Runs LISFLOOD-FP tile by tile, upstream to downstream, for each selected "
            "discharge. Each tile's downstream boundary condition is either a lake "
            "elevation, an optional downstream-boundary raster, or the elevation "
            "already simulated at the outlet of the tile immediately downstream. "
            "The boundary window is computed here at run time by walking along the "
            "downstream tile's actual result raster (or the downstream-boundary "
            "raster) - not pre-computed during Hydraulic simulations preparation - "
            "so it reflects that raster's real coverage rather than the zone's own "
            "DEM extent. Window size is capped at 4000m, or 1/4 of the zone's own "
            "perimeter if smaller. Tile elevation results are mosaicked together "
            "(maximum rule) into one raster per discharge, written directly into the "
            "simulations folder.\n\n"
            "If a LISFLOOD-FP simulation doesn't reach steady state by the expected "
            "time, it's automatically retried once without the -steady/-steadytol "
            "flags. Each tile's mass balance (Qin vs Qout, and Qin vs the inbci "
            "discharge) is checked after running and logged if outside a 5% "
            "tolerance - this doesn't stop the run, it's a QA flag in the log.\n\n"
            "Discharges are matched to their lake boundary condition by numeric "
            "suffix, not by list position or identical name: each inbci layer must "
            "be named 'inbci_<discharge>' (e.g. inbci_Q100, produced by joining "
            "Spatialize Flood Discharge output onto Tiles\\inbci.gpkg\\inbci) and "
            "have a field with that same name (e.g. Q100) holding the discharge "
            "values - other fields (join bookkeeping like fid/distance/etc.) are "
            "ignored. Select the matching boundary-condition fields on the lakes "
            "layer (e.g. z100 for Q100) with the Downstream boundary condition "
            "fields parameter - selection order doesn't matter, each is matched to "
            "its discharge by number.\n\n"
            "Inputs:\n"
            "- Tiles folder: contains envelopezones.gpkg, outbci.gpkg, and "
            "the per-zone DEM raster, all from Hydraulic simulations preparation "
            "(zoneN.tif only - the w/d/n/m zone rasters HydraulicSimPrep clips are "
            "temporary and converted straight to ASCII in the simulations folder, "
            "not kept here)\n"
            "- Inbci layers: one layer per discharge to simulate, e.g. inbci_Q20, "
            "inbci_Q100, inbci_Q350\n"
            "- Simulations folder: where LISFLOOD-FP run folders and mosaicked "
            "results (res_<discharge>) are written\n"
            "- LISFLOOD-FP folder: folder containing lisflood.exe\n"
            "- Output flow velocity?: also produce Vx/Vy rasters\n"
            "- Downstream boundary polygons (lakes)\n"
            "- Optional downstream boundary raster: if it has a valid value at a "
            "lake-boundary zone's exit point, overrides the lake polygon's field "
            "value for that zone\n"
            "- Downstream boundary condition fields: select one per discharge, "
            "each ending in that discharge's number (e.g. z100 for Q100)\n"
            "- Channel Manning's n (default 0.03)\n"
            "- Maximum simulation time in seconds (default 300000)\n"
            "- Courant-Friedrichs-Lewy condition (default 0.5)\n"
            "- D4 bed elevation raster\n\n"
            "Outputs:\n"
            "- Log file: timestamped log of simulations run, retries, mass-balance "
            "warnings, tiles skipped because of an error, and steady-state status\n"
            "- res_<discharge> rasters written directly into the simulations folder, "
            "one per discharge (not routed through a Processing sink, since the "
            "count and names depend on the inbci layers selected)\n"
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFile(
            self.TILES_FOLDER, "Tiles folder",
            behavior=QgsProcessingParameterFile.Folder,
        ))
        self.addParameter(QgsProcessingParameterMultipleLayers(
            self.INBCI_LAYERS, "Inbci layers, named inbci_<discharge> (e.g. inbci_Q20, inbci_Q100)",
            layerType=QgsProcessing.TypeVectorPoint,
        ))
        self.addParameter(QgsProcessingParameterFile(
            self.SIM_FOLDER, "Simulations folder",
            behavior=QgsProcessingParameterFile.Folder,
        ))
        self.addParameter(QgsProcessingParameterFile(
            self.LISFLOOD_FOLDER, "LISFLOOD-FP folder",
            behavior=QgsProcessingParameterFile.Folder,
        ))
        self.addParameter(QgsProcessingParameterBoolean(
            self.VOUTPUT, "Output flow velocity (Vx/Vy)?",
            defaultValue=False,
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.LAKES, "Downstream boundary polygons (lakes)",
            [QgsProcessing.TypeVectorPolygon],
        ))
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.LAKES_RASTER,
            "Optional: raster used for downstream boundary condition (overrides the lake polygons where it has a valid value)",
            optional=True,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.ZFIELDS, "Downstream boundary condition fields on lakes (one per discharge, e.g. z100)",
            parentLayerParameterName=self.LAKES,
            allowMultiple=True,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.CHANNEL_MANNING, "Channel Manning's n",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=0.03,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.SIM_TIME, "Maximum simulation time (s)",
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=300000,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.CFL, "Courant-Friedrichs-Lewy condition",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=0.5,
        ))
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.ZBED, "D4 bed elevation raster",
        ))
        self.addParameter(QgsProcessingParameterFileDestination(
            self.LOG, "Log file",
            fileFilter="Text files (*.txt)",
        ))

    def processAlgorithm(self, parameters, context, feedback):
        tiles_folder    = self.parameterAsFile(parameters, self.TILES_FOLDER, context)
        inbci_layers    = self.parameterAsLayerList(parameters, self.INBCI_LAYERS, context)
        sim_folder      = self.parameterAsFile(parameters, self.SIM_FOLDER, context)
        lisflood_folder = self.parameterAsFile(parameters, self.LISFLOOD_FOLDER, context)
        voutput         = self.parameterAsBoolean(parameters, self.VOUTPUT, context)
        lakes           = self.parameterAsVectorLayer(parameters, self.LAKES, context)
        lakes_raster    = self.parameterAsRasterLayer(parameters, self.LAKES_RASTER, context)
        zfields         = self.parameterAsStrings(parameters, self.ZFIELDS, context)
        channel_manning = self.parameterAsDouble(parameters, self.CHANNEL_MANNING, context)
        sim_time        = self.parameterAsInt(parameters, self.SIM_TIME, context)
        cfl             = self.parameterAsDouble(parameters, self.CFL, context)
        zbed            = self.parameterAsRasterLayer(parameters, self.ZBED, context)
        log_path        = self.parameterAsFileOutput(parameters, self.LOG, context)

        if not inbci_layers:
            raise QgsProcessingException("Select at least one inbci layer")
        if not zfields:
            raise QgsProcessingException("Select at least one downstream boundary condition field on the lakes layer")
        if not all([lakes, zbed]):
            raise QgsProcessingException("One or more input layers are invalid")

        run_hydraulic_simulations(
            tiles_folder=tiles_folder,
            inbci_layers=inbci_layers,
            sim_folder=sim_folder,
            lisflood_folder=lisflood_folder,
            voutput=voutput,
            lakes=lakes,
            lakes_raster_path=lakes_raster.source() if lakes_raster else None,
            zfields=zfields,
            channel_manning=channel_manning,
            sim_time=sim_time,
            cfl=cfl,
            zbed_path=zbed.source(),
            log_path=log_path,
            feedback=feedback,
        )

        return {self.LOG: log_path}


# =============================================================================
# Logging / QA helpers
# =============================================================================

def _log(filelog, feedback, level, message):
    """Writes a timestamped line to the log file and mirrors it to feedback
    (pushInfo for INFO, pushWarning for WARNING/ERROR)."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    filelog.write(f"[{timestamp}] [{level}] {message}\n")
    filelog.flush()
    if level == "INFO":
        feedback.pushInfo(message)
    else:
        feedback.pushWarning(f"[{level}] {message}")


def _read_last_mass_line(mass_file_path):
    """Returns the last data line of a .mass file as a list of fields, or
    None if the file doesn't exist or has no data lines."""
    if not os.path.exists(mass_file_path):
        return None
    with open(mass_file_path, "r") as f:
        lines = f.readlines()
    data_lines = [line for line in lines if line.strip() and not line.startswith("Time")]
    if not data_lines:
        return None
    return data_lines[-1].split()


def check_simulation_time(mass_file_path):
    """True if the simulation stopped at or before STEADY_TIME_THRESHOLD,
    meaning steady state likely wasn't reached and a retry without -steady
    is worth trying."""
    fields = _read_last_mass_line(mass_file_path)
    if fields is None:
        return False
    try:
        return float(fields[0]) <= STEADY_TIME_THRESHOLD
    except (ValueError, IndexError):
        return False


def check_mass_file(mass_file_path, lastdischarge, zonename, filelog, feedback):
    """Logs a warning (does not raise) if Qin/Qout disagree, or if Qin/Qout
    disagree with the inbci discharge, by more than MASS_BALANCE_TOLERANCE."""
    fields = _read_last_mass_line(mass_file_path)
    if fields is None:
        _log(filelog, feedback, "WARNING", f"Mass file not found or empty for {zonename}: {mass_file_path}")
        return
    # Columns (0-indexed): Time, Tstep, MinTstep, NumTsteps, Area, Vol, Qin, Hds, Qout
    try:
        qin = float(fields[6])
        qout = float(fields[8])
    except (ValueError, IndexError):
        _log(filelog, feedback, "WARNING", f"Could not parse Qin/Qout from mass file for {zonename}")
        return

    qin_qout_diff = abs(qout - qin) / abs(qin) if qin != 0 else abs(qout - qin)
    if qin_qout_diff > MASS_BALANCE_TOLERANCE:
        _log(filelog, feedback, "WARNING",
             f"Qin/Qout mismatch for {zonename}: Qin={qin:.3f}, Qout={qout:.3f} "
             f"({qin_qout_diff * 100:.1f}%)")

    if lastdischarge != 0:
        qin_disch_diff = abs(qin - lastdischarge) / abs(lastdischarge)
    else:
        qin_disch_diff = abs(qin - lastdischarge)
    if qin_disch_diff > MASS_BALANCE_TOLERANCE:
        _log(filelog, feedback, "WARNING",
             f"Qin does not match inbci discharge for {zonename}: Qin={qin:.3f}, "
             f"expected={lastdischarge:.3f} ({qin_disch_diff * 100:.1f}%)")


# =============================================================================
# Raster grid helper - mirrors the ArcGIS RasterIO interface (XtoCol/YtoRow/
# ColtoX/RowtoY/getValue/extent) closely enough to translate the exit-window
# walk almost line for line.
# =============================================================================

class _RasterGrid:
    def __init__(self, path):
        ds = gdal.Open(path)
        if ds is None:
            raise QgsProcessingException(f"Could not open raster: {path}")
        self.gt = ds.GetGeoTransform()
        band = ds.GetRasterBand(1)
        self.nodata = band.GetNoDataValue()
        self.array = band.ReadAsArray().astype(np.float64)
        self.rows, self.cols = self.array.shape
        self.cell_w = self.gt[1]
        self.cell_h = abs(self.gt[5])
        ds = None

    def x_to_col(self, x):
        return int((x - self.gt[0]) / self.gt[1])

    def y_to_row(self, y):
        return int((y - self.gt[3]) / self.gt[5])

    def col_to_x(self, col):
        return self.gt[0] + (col + 0.5) * self.gt[1]

    def row_to_y(self, row):
        return self.gt[3] + (row + 0.5) * self.gt[5]

    def in_bounds(self, row, col):
        return 0 <= row < self.rows and 0 <= col < self.cols

    def get_value(self, row, col):
        if not self.in_bounds(row, col):
            return None
        return float(self.array[row, col])

    def is_nodata_at(self, row, col):
        val = self.get_value(row, col)
        if val is None:
            return True
        if self.nodata is None:
            return False
        return np.float32(val) == np.float32(self.nodata)

    @property
    def xmin(self):
        return self.gt[0]

    @property
    def ymax(self):
        return self.gt[3]

    @property
    def xmax(self):
        return self.gt[0] + self.cols * self.gt[1]

    @property
    def ymin(self):
        return self.gt[3] + self.rows * self.gt[5]


def _sample_offset(res_grid, ref_grid, row, col, side):
    """Value of res_grid at the cell just outside the zone boundary, at the
    location of ref_grid's (row, col) cell centre. 'Just outside' means one
    cell further out in the direction 'side' points (the zone's own exit
    side), independent of which way the walk itself is progressing."""
    x = ref_grid.col_to_x(col)
    y = ref_grid.row_to_y(row)
    r = res_grid.y_to_row(y)
    c = res_grid.x_to_col(x)
    if side == "W":
        c -= 1
    elif side == "E":
        c += 1
    elif side == "N":
        r -= 1
    elif side == "S":
        r += 1
    val = res_grid.get_value(r, c)
    if val is None:
        return None
    # Compare in float32 precision, not float64: res_grid.array is stored as
    # float64 (upcast from the source's native float32), and for
    # extreme-magnitude nodata sentinels (e.g. -3.4028235e38, the edge of
    # float32 range) an exact float64 equality check can silently fail even
    # when the cell genuinely is nodata - the upcast value and the nodata
    # tag's own float64 parse can differ by the last bit or two. Rounding
    # both to float32 before comparing avoids that false negative.
    if res_grid.nodata is not None and np.float32(val) == np.float32(res_grid.nodata):
        return None
    return val


def _write_hvar(filebci, filebdy, side, lim_a, lim_b, zdep, hfix, sim_time, numhvar):
    """Appends one HVAR line to the .bci file and its matching hvar block to
    the .bdy file, and returns numhvar + 1."""
    filebci.write(f"{side}\t{lim_a:.2f}\t{lim_b:.2f}\tHVAR\thvar{numhvar}\n")
    filebdy.write(f"\nhvar{numhvar}\n")
    filebdy.write("4\tseconds\n")
    filebdy.write(f"{zdep:.2f}\t0\n")
    filebdy.write(f"{zdep:.2f}\t50000\n")
    filebdy.write(f"{hfix:.2f}\t55000\n")
    filebdy.write(f"{hfix:.2f}\t{sim_time}")
    return numhvar + 1


def _write_downstream_boundary(
    filebci, filebdy, ref_grid, res_grid, lakebci, hfix_lake, side, outpoint_x, outpoint_y,
    distoutput, zbed_grid, sim_time, numhvar,
):
    """
    Writes the downstream boundary condition to the .bci/.bdy files: walks
    outward from the outbci exit point along the zone's own boundary side in
    both directions, up to distoutput/2 each way (or until the zone's DEM
    extent ends), sampling the downstream elevation at each step.

    For a lake boundary condition (lakebci=True), hfix_lake is constant and
    a single window is written spanning the full walked distance on each
    side (plus a second window if the walk turned 90 degrees onto an
    adjacent side because the zone was too small to fit the full window on
    one edge).

    For a raster-based boundary condition (lakebci=False, from an already-
    simulated downstream tile or the optional downstream-boundary raster),
    a separate one-cell-wide HVAR window is written at every step where the
    downstream raster has a valid (non-nodata) value there, so the boundary
    elevation can vary along the tile edge to match what's actually been
    simulated next door.

    Mirrors ArcGIS_dev's execute_RunSim_prev exit-window block exactly,
    translated from RasterIO/arcpy to _RasterGrid/gdal.
    """
    if side in ("W", "E"):
        primary_axis_row = True
    else:
        primary_axis_row = False

    def sample_and_maybe_write(row, col, lim_a, lim_b, cur_side):
        nonlocal numhvar
        if lakebci:
            return
        ref_val = ref_grid.get_value(row, col)
        if ref_val is None:
            return
        hfix = _sample_offset(res_grid, ref_grid, row, col, cur_side)
        if hfix is None:
            return
        zdep = min(ref_val + 0.3, hfix)
        numhvar = _write_hvar(filebci, filebdy, cur_side, lim_a, lim_b, zdep, hfix, sim_time, numhvar)

    def walk_primary(sign, write_initial):
        """One pass from the outbci point, in the +1 or -1 direction along
        the zone's own exit side. Returns (lim, turned_side2, lim3, lim4)."""
        nonlocal numhvar
        col = ref_grid.x_to_col(outpoint_x)
        row = ref_grid.y_to_row(outpoint_y)

        if primary_axis_row:
            row_inc, col_inc = sign, 0
            dist_inc = ref_grid.cell_h
            lim = outpoint_y - sign * dist_inc / 2.0
        else:
            row_inc, col_inc = 0, sign
            dist_inc = ref_grid.cell_w
            lim = outpoint_x + sign * dist_inc / 2.0

        # Outbci point's own cell — written once total, on the first call only,
        # centered on the true outpoint coordinate (matches dev's shape.Y/X ± distinc/2)
        if not lakebci and write_initial:
            center = outpoint_y if primary_axis_row else outpoint_x
            sample_and_maybe_write(row, col, center - dist_inc / 2.0, center + dist_inc / 2.0, side)

        distance = 0.0
        while ref_grid.in_bounds(row, col) and distance < distoutput / 2.0:
            distance += dist_inc
            row += row_inc
            col += col_inc
            lim = ref_grid.row_to_y(row) if primary_axis_row else ref_grid.col_to_x(col)
            sample_and_maybe_write(row, col, lim - dist_inc / 2.0, lim + dist_inc / 2.0, side)

        # Back up to the last in-bounds cell
        row -= row_inc
        col -= col_inc

        side2 = "0"
        lim3 = 0.0
        lim4 = 0.0

        if distance < distoutput / 2.0:
            # Ran out of raster before filling the window - turn 90 degrees
            distance -= dist_inc
            if side == "W":
                row_inc2, col_inc2, dist_inc2 = 0, 1, ref_grid.cell_w
                lim3 = ref_grid.xmin + (col + 0.5) * ref_grid.cell_w
                side2 = "S" if sign == 1 else "N"
            elif side == "E":
                row_inc2, col_inc2, dist_inc2 = 0, -1, ref_grid.cell_w
                lim3 = ref_grid.xmin + (col + 0.5) * ref_grid.cell_w
                side2 = "S" if sign == 1 else "N"
            elif side == "N":
                row_inc2, col_inc2, dist_inc2 = 1, 0, ref_grid.cell_h
                lim3 = max(ref_grid.ymin, ref_grid.ymax - (row + 1) * ref_grid.cell_h) + 0.5 * ref_grid.cell_h
                side2 = "E" if sign == 1 else "W"
            else:  # side == "S"
                row_inc2, col_inc2, dist_inc2 = -1, 0, ref_grid.cell_h
                lim3 = max(ref_grid.ymin, ref_grid.ymax - (row + 1) * ref_grid.cell_h) + 0.5 * ref_grid.cell_h
                side2 = "E" if sign == 1 else "W"

            turn_row, turn_col = row, col
            while (ref_grid.in_bounds(turn_row, turn_col)
                   and not ref_grid.is_nodata_at(turn_row, turn_col)
                   and distance < distoutput / 2.0):
                distance += dist_inc2
                turn_row += row_inc2
                turn_col += col_inc2
                lim4 = ref_grid.row_to_y(turn_row) if side2 in ("W", "E") else ref_grid.col_to_x(turn_col)
                sample_and_maybe_write(turn_row, turn_col, lim4 - dist_inc2 / 2.0, lim4 + dist_inc2 / 2.0, side2)
            turn_row -= row_inc2
            turn_col -= col_inc2

            if lakebci and side2 != "0":
                filebci.write(f"{side2}\t{lim3:.2f}\t{lim4:.2f}\tHVAR\thvar\n")

        return lim, side2, lim3, lim4

    lim1, side2_fwd, lim3_fwd, lim4_fwd = walk_primary(sign=1, write_initial=True)
    lim2, side2_bwd, lim3_bwd, lim4_bwd = walk_primary(sign=-1, write_initial=False)

    if lakebci:
        row0 = zbed_grid.y_to_row(outpoint_y)
        col0 = zbed_grid.x_to_col(outpoint_x)
        zdep = min(zbed_grid.get_value(row0, col0) + 0.3, hfix_lake)
        filebci.write(f"{side}\t{lim1:.2f}\t{lim2:.2f}\tHVAR\thvar\n")
        filebdy.write("\nhvar\n")
        filebdy.write("4\tseconds\n")
        filebdy.write(f"{zdep:.2f}\t0\n")
        filebdy.write(f"{zdep:.2f}\t50000\n")
        filebdy.write(f"{hfix_lake:.2f}\t55000\n")
        filebdy.write(f"{hfix_lake:.2f}\t{sim_time}")
        numhvar += 1

    return numhvar


# =============================================================================
# Core logic
# =============================================================================

_BOUNDARY_FIELD_PATTERN = re.compile(r'^[A-Za-z]*\d+$')


def _boundary_field_for_discharge(dname, lakes_field_names):
    """Matches a discharge field (e.g. "Q100") to a lakes boundary-elevation
    field by trailing numeric suffix (e.g. "z100"), not by identical name -
    the lab's convention prefixes elevation fields with "z" rather than "Q"."""
    m = re.search(r'\d+$', dname)
    if not m:
        raise QgsProcessingException(
            f"Discharge field '{dname}' has no numeric suffix to match against "
            f"a lakes boundary-condition field"
        )
    suffix = m.group(0)
    candidates = [
        f for f in lakes_field_names
        if _BOUNDARY_FIELD_PATTERN.match(f) and f.endswith(suffix)
    ]
    if not candidates:
        raise QgsProcessingException(
            f"No boundary-condition field found on the lakes layer for discharge "
            f"'{dname}' (looked for a field ending in '{suffix}', e.g. z{suffix})"
        )
    if len(candidates) > 1:
        raise QgsProcessingException(
            f"Multiple lakes fields match discharge '{dname}': {candidates} - "
            f"rename so only one ends in '{suffix}'"
        )
    return candidates[0]


def _discharge_field(layer):
    """The discharge field on an inbci_<discharge> layer, resolved from the
    layer's own name (e.g. "inbci_Q100" -> "Q100") rather than by scanning
    its fields. Avoids guessing among join-tool bookkeeping fields (fid, n,
    distance, feature_x/y, nearest_x/y, etc.) that tools like "Join
    attributes by nearest" leave behind alongside the actual joined column."""
    name = layer.name()
    prefix = "inbci_"
    if not name.lower().startswith(prefix):
        raise QgsProcessingException(
            f"Layer '{name}' isn't named 'inbci_<discharge>' (e.g. inbci_Q100) - "
            f"can't infer which field holds the discharge"
        )
    suffix = name[len(prefix):]
    for f in layer.fields():
        if f.name().lower() == suffix.lower():
            return f.name()
    raise QgsProcessingException(
        f"Layer '{name}' has no field named '{suffix}' to match its own name "
        f"(fields present: {[f.name() for f in layer.fields()]})"
    )


def _load_layer(path, name):
    layer = QgsVectorLayer(path, name, "ogr")
    if not layer.isValid():
        raise QgsProcessingException(f"Could not load {path}")
    return layer


def _first_vertex(geom):
    """Start vertex of a line geometry, or the point itself for a point geometry
    (outbci points are written as plain points by HydraulicSimPrep.py)."""
    if geom.type() == QgsWkbTypes.LineGeometry:
        line = geom.asMultiPolyline()[0] if geom.isMultipart() else geom.asPolyline()
        return line[0]
    return geom.asPoint()


def _sample_array(array, gt, point):
    col = int((point.x() - gt[0]) / gt[1])
    row = int((point.y() - gt[3]) / gt[5])
    return float(array[row, col])


def _write_par_file(sim_folder, simname, zone, sim_time, channel_manning, voutput, cfl):
    zonename = f"zone{zone}"
    par_path = os.path.join(sim_folder, f"{zonename}.par")
    with open(par_path, "w") as f:
        f.write(f"DEMfile\t{zonename}.txt\n")
        f.write(f"resroot\t{zonename}\n")
        f.write(f"dirroot\t{simname}\n")
        f.write(f"manningfile\tn{zonename}.txt\n")
        f.write(f"bcifile\t{simname}\\{zonename}.bci\n")
        f.write(f"sim_time\t{sim_time}\n")
        f.write(f"saveint\t{sim_time}\n")
        # LISFLOOD-FP expects its own path separator here (bdyfile is
        # "<dirroot>\\<zone>.bdy"), independent of the host OS - keep the
        # literal backslash.
        f.write(f"bdyfile\t{simname}\\{zonename}.bdy\n")
        f.write(f"SGCwidth\tw{zonename}.txt\n")
        f.write(f"SGCbank\t{zonename}.txt\n")
        f.write(f"SGCbed\td{zonename}.txt\n")
        f.write(f"SGCn\t{channel_manning}\n")
        f.write(f"chanmask\tm{zonename}.txt\n")
        if voutput:
            f.write("hazard\n")
            f.write("qoutput\n")
        f.write(f"cfl\t{cfl}\n")
        f.write("max_Froude\t1\n")


def _write_bdy_file(bdy_path, segment, zone, dname, cellsize, sim_time):
    """Writes the main inflow plus any lateral inflows for this zone. Returns
    the main point's discharge, needed afterwards for the steadytol calc."""
    zonename = f"zone{zone}"
    lastdischarge = None
    latnum = 0

    with open(bdy_path, "w") as f:
        for point in sorted(segment, key=lambda p: p["flowacc"]):
            q_value = point[dname]

            if point["type"] == "main":
                pointdischarge = q_value / cellsize
                lastdischarge = q_value
                f.write(f"{zonename}.bdy\n")
                f.write(f"{zonename}\n")
                f.write("3\tseconds\n")
                f.write("0\t0\n")
                f.write(f"{pointdischarge:.3f}\t50000\n")
                f.write(f"{pointdischarge:.3f}\t{sim_time}")
            else:
                latnum += 1
                pointdischarge = (q_value - lastdischarge) / cellsize
                lastdischarge = q_value
                f.write(f"\n{zonename}_{latnum}\n")
                f.write("3\tseconds\n")
                f.write("0\t0\n")
                f.write(f"{pointdischarge:.3f}\t50000\n")
                f.write(f"{pointdischarge:.3f}\t{sim_time}")

    if lastdischarge is None:
        raise RuntimeError(f"No main inflow point found for {zonename}")

    return lastdischarge


def _compute_steadytol(lastdischarge):
    """1 significant figure, ~0.5% of the main inflow discharge."""
    tol = lastdischarge / 200.0
    decimals = -int(math.floor(math.log10(abs(tol))))
    return str(round(tol, decimals))


def _run_lisflood(lisflood_exe, par_path, sim_folder, steady, steadytol, timeout):
    cmd = [lisflood_exe]
    if steady:
        cmd += ["-steady", "-steadytol", steadytol]
    cmd += [par_path]
    result = subprocess.run(
        cmd, cwd=sim_folder, capture_output=True, text=True,
        timeout=timeout, shell=True,
    )
    return result


def _remove_if_exists(path):
    if os.path.exists(path):
        os.remove(path)


def _collect_outputs(currentsimfolder, zonename, voutput, crs_wkt):
    """Renames LISFLOOD-FP's ASCII outputs and converts them to rasters.
    Returns True if steady state was reached (a "-9999.elev" file was
    produced), False if LISFLOOD-FP stopped at max sim_time instead
    ("-0001.elev")."""
    elev_txt = os.path.join(currentsimfolder, f"{zonename}elev.txt")
    _remove_if_exists(elev_txt)

    steady_elev = os.path.join(currentsimfolder, f"{zonename}-9999.elev")
    if os.path.exists(steady_elev):
        os.rename(steady_elev, elev_txt)
        steady = True
    else:
        final_elev = os.path.join(currentsimfolder, f"{zonename}-0001.elev")
        if not os.path.exists(final_elev):
            raise RuntimeError(f"No elevation output file found for {zonename}")
        os.rename(final_elev, elev_txt)
        steady = False

    if voutput:
        vx_txt = os.path.join(currentsimfolder, f"{zonename}Vx.txt")
        vy_txt = os.path.join(currentsimfolder, f"{zonename}Vy.txt")
        _remove_if_exists(vx_txt)
        _remove_if_exists(vy_txt)

        vx_steady = os.path.join(currentsimfolder, f"{zonename}-9999.Vx")
        vy_steady = os.path.join(currentsimfolder, f"{zonename}-9999.Vy")
        vx_final  = os.path.join(currentsimfolder, f"{zonename}-0001.Vx")
        vy_final  = os.path.join(currentsimfolder, f"{zonename}-0001.Vy")

        if os.path.exists(vx_steady):
            os.rename(vx_steady, vx_txt)
            os.rename(vy_steady, vy_txt)
        elif os.path.exists(vx_final):
            os.rename(vx_final, vx_txt)
            os.rename(vy_final, vy_txt)

        if os.path.exists(vx_txt):
            _ascii_to_raster(vx_txt, os.path.join(currentsimfolder, f"Vx_{zonename}.{RASTER_EXT}"), crs_wkt)
            _ascii_to_raster(vy_txt, os.path.join(currentsimfolder, f"Vy_{zonename}.{RASTER_EXT}"), crs_wkt)

    elev_out = os.path.join(currentsimfolder, f"elev_{zonename}.{RASTER_EXT}")
    _ascii_to_raster(elev_txt, elev_out, crs_wkt)

    return steady


def _ascii_to_raster(ascii_path, out_path, crs_wkt):
    gdal.Translate(out_path, ascii_path, format="GTiff", outputSRS=crs_wkt)


def _mosaic_max(existing_path, new_path, out_path):
    """Merges new_path into existing_path using a maximum rule, extending the
    extent as needed - equivalent to arcpy Mosaic_management(..., "MAXIMUM").
    out_path may be the same as existing_path."""
    tmp_out = out_path + ".tmp.tif"

    ds_a = gdal.Open(existing_path)
    ds_b = gdal.Open(new_path)

    gt = ds_a.GetGeoTransform()
    px_w, px_h = gt[1], gt[5]

    def bounds(ds):
        g = ds.GetGeoTransform()
        xmin = g[0]
        ymax = g[3]
        xmax = xmin + g[1] * ds.RasterXSize
        ymin = ymax + g[5] * ds.RasterYSize
        return xmin, ymin, xmax, ymax

    xmin_a, ymin_a, xmax_a, ymax_a = bounds(ds_a)
    xmin_b, ymin_b, xmax_b, ymax_b = bounds(ds_b)

    xmin = min(xmin_a, xmin_b)
    xmax = max(xmax_a, xmax_b)
    ymin = min(ymin_a, ymin_b)
    ymax = max(ymax_a, ymax_b)

    cols = int(round((xmax - xmin) / px_w))
    rows = int(round((ymax - ymin) / abs(px_h)))

    nodata = ds_a.GetRasterBand(1).GetNoDataValue()
    if nodata is None:
        nodata = -9999.0

    out_array = np.full((rows, cols), nodata, dtype=np.float32)

    def paste(ds):
        g = ds.GetGeoTransform()
        band = ds.GetRasterBand(1)
        nd = band.GetNoDataValue()
        data = band.ReadAsArray().astype(np.float32)
        if nd is not None:
            data = np.where(data == nd, nodata, data)

        col_off = int(round((g[0] - xmin) / px_w))
        row_off = int(round((ymax - g[3]) / abs(px_h)))
        sub = out_array[row_off:row_off + ds.RasterYSize, col_off:col_off + ds.RasterXSize]

        valid = data != nodata
        current_valid = sub != nodata
        both = valid & current_valid
        sub[both] = np.maximum(sub[both], data[both])
        only_new = valid & ~current_valid
        sub[only_new] = data[only_new]

    paste(ds_a)
    paste(ds_b)

    projection = ds_a.GetProjection()
    ds_a = None
    ds_b = None

    driver = gdal.GetDriverByName("GTiff")
    out_ds = driver.Create(tmp_out, cols, rows, 1, gdal.GDT_Float32)
    out_ds.SetGeoTransform((xmin, px_w, 0, ymax, 0, px_h))
    out_ds.SetProjection(projection)
    band_out = out_ds.GetRasterBand(1)
    band_out.SetNoDataValue(nodata)
    band_out.WriteArray(out_array)
    out_ds.FlushCache()
    out_ds = None

    shutil.move(tmp_out, out_path)


def run_hydraulic_simulations(
    tiles_folder,
    inbci_layers,
    sim_folder,
    lisflood_folder,
    voutput,
    lakes,
    lakes_raster_path,
    zfields,
    channel_manning,
    sim_time,
    cfl,
    zbed_path,
    log_path,
    feedback,
):
    """
    Runs LISFLOOD-FP zone by zone, upstream to downstream, once per selected
    inbci layer (one layer per discharge), and mosaics tile elevation results
    (maximum rule) into sim_folder/res_<discharge>.<RASTER_EXT>.

    The downstream boundary condition for a zone with no lake is computed
    here at run time by walking the zone's exit boundary and sampling the
    already-completed downstream tile's own result raster (or, if provided,
    an optional downstream-boundary raster) - mirroring ArcGIS_dev's
    execute_RunSim_prev. This replaces the earlier design where
    HydraulicSimPrep pre-computed a fixed exit window against the zone's own
    DEM extent at prep time.

    Args:
        tiles_folder       : str - folder with envelopezones.gpkg, outbci.gpkg,
                              and per-zone rasters
        inbci_layers        : list[QgsVectorLayer] - one per discharge, each
                              with zoneid/flowacc/type/fpid plus exactly one
                              discharge field (e.g. inbci_Q100 with field
                              "Q100")
        sim_folder          : str - folder for LISFLOOD-FP run folders and
                              res_<discharge> outputs (HydraulicSimPrep's
                              output folder; also where the template
                              zone{N}.bci files it wrote live)
        lisflood_folder      : str - folder containing lisflood.exe
        voutput             : bool - also produce Vx/Vy rasters
        lakes                : QgsVectorLayer - downstream boundary polygons;
                              must have one field per discharge, named to
                              match each inbci layer's discharge field
        lakes_raster_path    : str or None - optional raster whose value (if
                              valid) overrides a lake-boundary zone's fixed
                              elevation for that zone
        zfields              : list[str] - lakes fields selected as boundary
                              conditions (e.g. ["z20", "z100", "z350"]);
                              matched to discharges by numeric suffix, not by
                              list order
        channel_manning      : float - SGCn value
        sim_time             : int - sim_time / saveint (s)
        cfl                  : float - cfl value
        zbed_path            : str - path to the D4 bed elevation raster
        log_path             : str - path to the log file to write
        feedback             : QgsProcessingFeedback
    """

    outbci_path    = os.path.join(tiles_folder, "outbci.gpkg") + "|layername=outbci"
    envelopezones_path = os.path.join(tiles_folder, "envelopezones.gpkg") + "|layername=envelopezones"
    lisflood_exe   = os.path.join(lisflood_folder, "lisflood.exe")

    # ------------------------------------------------------------------
    # Discharges: pair each selected inbci layer with its discharge name,
    # and confirm the lakes layer has a matching field for each.
    # ------------------------------------------------------------------
    discharge_layers = []
    seen_names = set()
    for layer in inbci_layers:
        dname = _discharge_field(layer)
        if dname in seen_names:
            raise QgsProcessingException(f"Discharge field '{dname}' selected more than once")
        seen_names.add(dname)
        discharge_layers.append((dname, layer))
    discharge_layers.sort(key=lambda t: t[0])

    lakes_field_names = [f.name() for f in lakes.fields()]
    boundary_field_by_discharge = {}
    errors = []
    for dname, _ in discharge_layers:
        try:
            boundary_field_by_discharge[dname] = _boundary_field_for_discharge(dname, zfields)
        except QgsProcessingException as e:
            errors.append(str(e))
    if errors:
        raise QgsProcessingException("; ".join(errors))

    unused_zfields = set(zfields) - set(boundary_field_by_discharge.values())
    if unused_zfields:
        feedback.pushWarning(
            f"Selected boundary field(s) not matched to any discharge, ignored: {sorted(unused_zfields)}"
        )

    # ------------------------------------------------------------------
    # outbci (outlet point + side per zone) and envelopezones (lake id +
    # extent per zone) - invariant across discharges
    # ------------------------------------------------------------------
    feedback.pushInfo("Loading outbci and envelopezones...")

    outbci_layer = _load_layer(outbci_path, "outbci")
    listzonesout = {}
    for feat in outbci_layer.getFeatures():
        listzonesout[int(feat["zoneid"])] = (feat["side"], _first_vertex(feat.geometry()))

    envelopezones_layer = _load_layer(envelopezones_path, "envelopezones")
    lakeid_byzone = {}
    dict_outputwindow = {}
    for feat in envelopezones_layer.getFeatures():
        zone_id = int(feat["GRID_CODE"])
        lake_id = feat["Lake_ID"]
        if lake_id is not None and int(lake_id) != -999:
            lakeid_byzone[zone_id] = int(lake_id)

        ext = feat.geometry().boundingBox()
        perimeter = 2 * (ext.width() + ext.height())
        dict_outputwindow[zone_id] = min(MAX_DISTOUTPUT, perimeter / 4.0)

    # lake feature id (fid) -> feature, for hfix lookups by discharge field name
    lakes_by_id = {feat.id(): feat for feat in lakes.getFeatures()}

    used_lake_ids = set(lakeid_byzone.values())
    missing_values = []
    for dname, boundary_field in boundary_field_by_discharge.items():
        for lake_id in used_lake_ids:
            feat = lakes_by_id.get(lake_id)
            if feat is None:
                missing_values.append(f"lake fid={lake_id} (used by a zone) not found in lakes layer")
            elif feat[boundary_field] is None:
                label = feat["WATERBODY_"] if "WATERBODY_" in lakes_field_names else lake_id
                missing_values.append(f"lake fid={lake_id} ({label}): {boundary_field} is NULL for {dname}")
    if missing_values:
        raise QgsProcessingException(
            "Missing downstream boundary elevation(s):\n" + "\n".join(missing_values)
        )

    # ------------------------------------------------------------------
    # Optional downstream-boundary raster, loaded once
    # ------------------------------------------------------------------
    lakes_raster_grid = None
    if lakes_raster_path:
        try:
            lakes_raster_grid = _RasterGrid(lakes_raster_path)
        except QgsProcessingException as e:
            feedback.pushWarning(f"Could not load downstream boundary raster, ignoring it: {e}")

    # ------------------------------------------------------------------
    # Reference CRS: any zone raster works
    # ------------------------------------------------------------------
    first_dname, first_layer = discharge_layers[0]
    any_zone = next(int(f["zoneid"]) for f in first_layer.getFeatures())
    ref_path = os.path.join(tiles_folder, f"zone{any_zone}.{RASTER_EXT}")
    ref_ds = gdal.Open(ref_path)
    if ref_ds is None:
        raise QgsProcessingException(f"Could not open reference raster: {ref_path}")
    ref_crs_wkt = ref_ds.GetProjection()
    ref_ds = None

    zbed_grid_full = _RasterGrid(zbed_path)

    progress = 0
    total_steps = None  # computed once zones are known for the first discharge

    with open(log_path, "w") as filelog:
        for dname, inbci_layer in discharge_layers:
            simname = dname

            # ------------------------------------------------------------
            # Load this discharge's inbci points, grouped by zone
            # ------------------------------------------------------------
            feedback.pushInfo(f"Loading discharge points for {simname}...")

            dictsegmentsin = {}
            for feat in inbci_layer.getFeatures():
                zoneid = int(feat["zoneid"])
                point = {
                    "zoneid":  zoneid,
                    "flowacc": float(feat["flowacc"]),
                    "type":    feat["type"],
                    "fpid":    feat["fpid"],
                    dname:     feat[dname],
                }
                dictsegmentsin.setdefault(zoneid, []).append(point)

            if not dictsegmentsin:
                raise QgsProcessingException(f"{inbci_layer.name()} contains no points")

            allzones = sorted(dictsegmentsin.keys())

            # Zone order: by floodplain group (ascending fpid), zones within a
            # group descending - mirrors the ArcGIS tool's upstream-to-
            # downstream ordering
            dictzones_fp = {}
            for zone in allzones:
                fpid = dictsegmentsin[zone][0]["fpid"]
                dictzones_fp.setdefault(fpid, []).append(zone)

            sortedzones = []
            for fpid in sorted(dictzones_fp.keys()):
                sortedzones.extend(sorted(dictzones_fp[fpid], reverse=True))

            if total_steps is None:
                total_steps = len(sortedzones) * len(discharge_layers)

            currentsimfolder = os.path.join(sim_folder, simname)
            currentresult = os.path.join(sim_folder, f"res_{simname}.{RASTER_EXT}")
            os.makedirs(currentsimfolder, exist_ok=True)

            if os.path.exists(currentresult):
                _log(filelog, feedback, "INFO", f"Simulation result already exists for {simname}. Skipping.")
                progress += len(sortedzones)
                feedback.setProgress(100 * progress / total_steps)
                continue

            skipsim = False

            for zone in sortedzones:
                segment = dictsegmentsin[zone]
                main_points = [p for p in segment if p["type"] == "main"]

                if skipsim or not main_points:
                    progress += 1
                    feedback.setProgress(100 * progress / total_steps)
                    continue

                zonename = f"zone{zone}"
                elev_out_path = os.path.join(currentsimfolder, f"elev_{zonename}.{RASTER_EXT}")

                try:
                    if not os.path.exists(elev_out_path):
                        _log(filelog, feedback, "INFO", f"Running simulation on zone {zone}, sim {simname}")

                        distoutput = dict_outputwindow[zone]
                        out_side, outpoint = listzonesout[zone]
                        ref_grid = _RasterGrid(os.path.join(tiles_folder, f"zone{zone}.{RASTER_EXT}"))

                        # ----------------------------------------------
                        # Find the downstream elevation source: a lake, an
                        # optional downstream-boundary raster overriding
                        # that lake, or the already-simulated tile below.
                        # ----------------------------------------------
                        lakebci = False
                        hfix_lake = None
                        res_grid = None
                        tmp_res_path = None

                        if zone in lakeid_byzone:
                            lake_feat = lakes_by_id[lakeid_byzone[zone]]
                            hfix_lake = lake_feat[boundary_field_by_discharge[dname]]
                            lakebci = True

                            if lakes_raster_grid is not None:
                                override_val = _sample_offset(lakes_raster_grid, ref_grid,
                                                               ref_grid.y_to_row(outpoint.y()),
                                                               ref_grid.x_to_col(outpoint.x()),
                                                               out_side)
                                if override_val is not None:
                                    res_grid = lakes_raster_grid
                                    lakebci = False
                                    _log(filelog, feedback, "INFO",
                                         f"Zone {zone}: using downstream boundary raster override")
                                else:
                                    _log(filelog, feedback, "INFO",
                                         f"Zone {zone}: using lake boundary condition (z={hfix_lake:.2f})")
                        else:
                            if not os.path.exists(currentresult):
                                raise RuntimeError(f"Downstream boundary condition not found: tile #{zone}")
                            tmp_res_path = os.path.join(currentsimfolder, f"tmp_{zonename}.{RASTER_EXT}")
                            _remove_if_exists(tmp_res_path)
                            shutil.copy(currentresult, tmp_res_path)
                            res_grid = _RasterGrid(tmp_res_path)

                        # ----------------------------------------------
                        # .bci: copy the P-lines-only template HydraulicSimPrep
                        # wrote, strip any non-P lines defensively, then
                        # append the downstream HVAR window(s) below
                        # ----------------------------------------------
                        source_bci = os.path.join(sim_folder, f"{zonename}.bci")
                        destination_bci = os.path.join(currentsimfolder, f"{zonename}.bci")
                        _remove_if_exists(destination_bci)
                        shutil.copy(source_bci, destination_bci)
                        with open(destination_bci, "r") as f:
                            lines = f.readlines()
                        with open(destination_bci, "w") as f:
                            for line in lines:
                                if line.strip() and line[0] == "P":
                                    f.write(line)

                        # ----------------------------------------------
                        # .bdy: inflow points first, then the downstream
                        # boundary window(s)
                        # ----------------------------------------------
                        bdy_path = os.path.join(currentsimfolder, f"{zonename}.bdy")
                        cellsize = (ref_grid.cell_w + ref_grid.cell_h) / 2.0
                        lastdischarge = _write_bdy_file(bdy_path, segment, zone, dname, cellsize, sim_time)

                        with open(destination_bci, "a") as filebci, open(bdy_path, "a") as filebdy:
                            _write_downstream_boundary(
                                filebci, filebdy, ref_grid, res_grid, lakebci, hfix_lake,
                                out_side, outpoint.x(), outpoint.y(), distoutput,
                                zbed_grid_full, sim_time, numhvar=1,
                            )

                        if tmp_res_path:
                            _remove_if_exists(tmp_res_path)

                        # ----------------------------------------------
                        # .par + run
                        # ----------------------------------------------
                        _write_par_file(sim_folder, simname, zone, sim_time, channel_manning, voutput, cfl)
                        steadytol = _compute_steadytol(lastdischarge)
                        par_path = os.path.join(sim_folder, f"{zonename}.par")

                        try:
                            result = _run_lisflood(lisflood_exe, par_path, sim_folder, True, steadytol, SIM_TIMEOUT)
                            if result.returncode != 0:
                                raise RuntimeError(
                                    f"LISFLOOD-FP failed (code {result.returncode}): {result.stderr[:500]}"
                                )
                        except subprocess.TimeoutExpired:
                            raise RuntimeError(f"LISFLOOD-FP timed out after {SIM_TIMEOUT}s")

                        mass_file_path = os.path.join(currentsimfolder, f"{zonename}.mass")

                        # ----------------------------------------------
                        # Retry without -steady if it stopped before steady
                        # state was reached
                        # ----------------------------------------------
                        if check_simulation_time(mass_file_path):
                            _log(filelog, feedback, "WARNING",
                                 f"{zonename} stopped before steady state (sim {simname}); retrying without -steady")
                            for ext in ("-0001.elev", "-9999.elev", "-0001.Vx", "-9999.Vx",
                                        "-0001.Vy", "-9999.Vy"):
                                _remove_if_exists(os.path.join(currentsimfolder, f"{zonename}{ext}"))
                            _remove_if_exists(mass_file_path)

                            try:
                                result = _run_lisflood(lisflood_exe, par_path, sim_folder, False, None, SIM_TIMEOUT)
                                if result.returncode != 0:
                                    raise RuntimeError(
                                        f"LISFLOOD-FP retry failed (code {result.returncode}): {result.stderr[:500]}"
                                    )
                            except subprocess.TimeoutExpired:
                                raise RuntimeError(f"LISFLOOD-FP retry timed out after {SIM_TIMEOUT}s")

                        check_mass_file(mass_file_path, lastdischarge, zonename, filelog, feedback)

                        steady = _collect_outputs(currentsimfolder, zonename, voutput, ref_crs_wkt)
                        if not steady:
                            _log(filelog, feedback, "WARNING",
                                 f"Steady state not reached: {zonename}, sim {simname} (using final-time output)")

                    if not os.path.exists(currentresult):
                        shutil.copy(elev_out_path, currentresult)
                    else:
                        _mosaic_max(currentresult, elev_out_path, currentresult)

                except Exception as e:
                    _log(filelog, feedback, "ERROR", f"Sim aborted during zone {zone}, {simname}: {e}")
                    feedback.pushWarning(f"Simulation for {simname} skipped from zone {zone} onward. See log file.")
                    skipsim = True

                progress += 1
                feedback.setProgress(100 * progress / total_steps)

        _log(filelog, feedback, "INFO", "=" * 80)
        _log(filelog, feedback, "INFO", "SIMULATION EXECUTION COMPLETED")
        _log(filelog, feedback, "INFO", "=" * 80)