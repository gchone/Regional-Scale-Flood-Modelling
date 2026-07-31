import math
import os
import shutil
import subprocess
import sys
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


class RunHydraulicSimulations(QgsProcessingAlgorithm):

    TILES_FOLDER    = "TILES_FOLDER"
    INBCI_LAYERS    = "INBCI_LAYERS"
    SIM_FOLDER      = "SIM_FOLDER"
    LISFLOOD_FOLDER = "LISFLOOD_FOLDER"
    VOUTPUT         = "VOUTPUT"
    LAKES           = "LAKES"
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
            "elevation or the elevation already simulated at the outlet of the tile "
            "immediately downstream. Tile elevation results are mosaicked together "
            "(maximum rule) into one raster per discharge, written directly into the "
            "simulations folder.\n\n"
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
            "- Tiles folder: contains polyzones.gpkg (from Tiling), outbci.gpkg, and "
            "the per-zone DEM raster from Hydraulic simulations preparation "
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
            "- Downstream boundary condition fields: select one per discharge, "
            "each ending in that discharge's number (e.g. z100 for Q100)\n"
            "- Channel Manning's n (default 0.03)\n"
            "- Maximum simulation time in seconds (default 300000)\n"
            "- Courant-Friedrichs-Lewy condition (default 0.5)\n"
            "- D4 bed elevation raster\n\n"
            "Outputs:\n"
            "- Log file: records simulations where steady state was not reached, and "
            "any tile skipped because of an error\n"
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
        zfields         = self.parameterAsFields(parameters, self.ZFIELDS, context)
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
# Core logic
# =============================================================================

import re

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


def run_hydraulic_simulations(
    tiles_folder,
    inbci_layers,
    sim_folder,
    lisflood_folder,
    voutput,
    lakes,
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

    Args:
        tiles_folder    : str - folder with polyzones.gpkg, outbci.gpkg, and
                           per-zone rasters
        inbci_layers    : list[QgsVectorLayer] - one per discharge, each with
                           zoneid/flowacc/type/fpid plus exactly one discharge
                           field (e.g. inbci_Q100 with field "Q100")
        sim_folder      : str - folder for LISFLOOD-FP run folders and
                           res_<discharge> outputs (HydraulicSimPrep's output
                           folder)
        lisflood_folder : str - folder containing lisflood.exe
        voutput         : bool - also produce Vx/Vy rasters
        lakes           : QgsVectorLayer - downstream boundary polygons; must
                           have one field per discharge, named to match each
                           inbci layer's discharge field
        zfields         : list[str] - lakes fields selected as boundary
                           conditions (e.g. ["z20", "z100", "z350"]); matched
                           to discharges by numeric suffix, not by list order
        channel_manning : float - SGCn value
        sim_time        : int - sim_time / saveint (s)
        cfl             : float - cfl value
        zbed_path       : str - path to the D4 bed elevation raster
        log_path        : str - path to the log file to write
        feedback        : QgsProcessingFeedback
    """

    outbci_path        = os.path.join(tiles_folder, "outbci.gpkg") + "|layername=outbci"
    envelopezones_path = os.path.join(tiles_folder, "polyzones.gpkg") + "|layername=polyzones"
    lisflood_exe        = os.path.join(lisflood_folder, "lisflood.exe")

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
    # outbci (outlet point per zone) and polyzones (lake id per zone) -
    # invariant across discharges
    # ------------------------------------------------------------------
    feedback.pushInfo("Loading outbci and polyzones...")

    outbci_layer = _load_layer(outbci_path, "outbci")
    listzonesout = {}
    for feat in outbci_layer.getFeatures():
        listzonesout[int(feat["zoneid"])] = _first_vertex(feat.geometry())

    # NB: envelopezones.gpkg (from HydraulicSimPrep) only carries GRID_CODE,
    # not Lake_ID - polyzones.gpkg (from Tiling) is geometrically the same
    # rectangle and is where Lake_ID actually lives.
    envelopezones_layer = _load_layer(envelopezones_path, "polyzones")
    lakeid_byzone = {}
    for feat in envelopezones_layer.getFeatures():
        lake_id = feat["Lake_ID"]
        if lake_id is not None and int(lake_id) != -999:
            lakeid_byzone[int(feat["GRID_CODE"])] = int(lake_id)

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
    # Reference raster (cell size, CRS): any zone raster works
    # ------------------------------------------------------------------
    first_dname, first_layer = discharge_layers[0]
    any_zone = next(int(f["zoneid"]) for f in first_layer.getFeatures())
    ref_path = os.path.join(tiles_folder, f"zone{any_zone}.{RASTER_EXT}")
    ref_ds = gdal.Open(ref_path)
    if ref_ds is None:
        raise QgsProcessingException(f"Could not open reference raster: {ref_path}")
    ref_gt = ref_ds.GetGeoTransform()
    ref_crs_wkt = ref_ds.GetProjection()
    cellsize = (abs(ref_gt[1]) + abs(ref_gt[5])) / 2.0
    ref_ds = None

    zbed_ds = gdal.Open(zbed_path)
    if zbed_ds is None:
        raise QgsProcessingException(f"Could not open D4 bed elevation raster: {zbed_path}")
    zbed_gt = zbed_ds.GetGeoTransform()
    zbed_array = zbed_ds.GetRasterBand(1).ReadAsArray().astype(np.float64)
    zbed_ds = None

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
                        outpoint = listzonesout[zone]

                        if zone in lakeid_byzone:
                            lake_feat = lakes_by_id[lakeid_byzone[zone]]
                            hfix = lake_feat[boundary_field_by_discharge[dname]]
                        else:
                            if not os.path.exists(currentresult):
                                raise RuntimeError(
                                    f"Downstream boundary condition not found: tile #{zone}"
                                )
                            tmp_path = os.path.join(currentsimfolder, f"tmp_{zonename}.{RASTER_EXT}")
                            if os.path.exists(tmp_path):
                                os.remove(tmp_path)
                            shutil.copy(currentresult, tmp_path)
                            hfix, hfix_nodata = _get_raster_value(tmp_path, outpoint)
                            os.remove(tmp_path)
                            if hfix is None or hfix == hfix_nodata:
                                raise RuntimeError(
                                    f"Downstream boundary condition not found: tile #{zone}"
                                )

                        _write_par_file(
                            sim_folder, simname, zone, sim_time, channel_manning, voutput, cfl,
                        )

                        bdy_path = os.path.join(currentsimfolder, f"{zonename}.bdy")
                        lastdischarge = _write_bdy_file(bdy_path, segment, zone, dname, cellsize, sim_time)

                        zbed_val = _sample_array(zbed_array, zbed_gt, outpoint)
                        zdep = min(zbed_val + 0.3, hfix)
                        _append_bdy_downstream(bdy_path, zdep, hfix, sim_time)

                        steadytol = _compute_steadytol(lastdischarge)

                        par_path = os.path.join(sim_folder, f"{zonename}.par")
                        subprocess.check_call(
                            [lisflood_exe, "-steady", "-steadytol", steadytol, par_path],
                            cwd=sim_folder,
                        )

                        steady = _collect_outputs(
                            currentsimfolder, zonename, voutput, ref_crs_wkt,
                        )
                        if not steady:
                            msg = f"Steady state not reached: {zonename}, sim {simname}"
                            filelog.write(msg + "\n")
                            feedback.pushWarning(msg)

                    if not os.path.exists(currentresult):
                        shutil.copy(elev_out_path, currentresult)
                    else:
                        _mosaic_max(currentresult, elev_out_path, currentresult)

                except Exception as e:
                    filelog.write(f"ERROR in {simname}: sim aborted during zone {zone}: {e}\n")
                    feedback.pushWarning(
                        f"Simulation for {simname} skipped from zone {zone} onward. See log file."
                    )
                    skipsim = True

                progress += 1
                feedback.setProgress(100 * progress / total_steps)


# =============================================================================
# Helpers
# =============================================================================

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


def _get_raster_value(path, point):
    ds = gdal.Open(path)
    gt = ds.GetGeoTransform()
    band = ds.GetRasterBand(1)
    nodata = band.GetNoDataValue()
    col = int((point.x() - gt[0]) / gt[1])
    row = int((point.y() - gt[3]) / gt[5])
    if 0 <= col < ds.RasterXSize and 0 <= row < ds.RasterYSize:
        val = band.ReadAsArray(col, row, 1, 1)
        value = float(val[0][0]) if val is not None else None
    else:
        value = None
    ds = None
    return value, nodata


def _write_par_file(sim_folder, simname, zone, sim_time, channel_manning, voutput, cfl):
    zonename = f"zone{zone}"
    par_path = os.path.join(sim_folder, f"{zonename}.par")
    with open(par_path, "w") as f:
        f.write(f"DEMfile\t{zonename}.txt\n")
        f.write(f"resroot\t{zonename}\n")
        f.write(f"dirroot\t{simname}\n")
        f.write(f"manningfile\tn{zonename}.txt\n")
        f.write(f"bcifile\t{zonename}.bci\n")
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


def _append_bdy_downstream(bdy_path, zdep, hfix, sim_time):
    """Appends the downstream boundary (hvar): starts 0.3 m above the bed,
    ramps to the fixed boundary elevation."""
    with open(bdy_path, "a") as f:
        f.write("\nhvar\n")
        f.write("4\tseconds\n")
        f.write(f"{zdep:.2f}\t0\n")
        f.write(f"{zdep:.2f}\t50000\n")
        f.write(f"{hfix:.2f}\t55000\n")
        f.write(f"{hfix:.2f}\t{sim_time}")


def _compute_steadytol(lastdischarge):
    """1 significant figure, ~0.5% of the main inflow discharge."""
    tol = lastdischarge / 200.0
    decimals = -int(math.floor(math.log10(abs(tol))))
    return str(round(tol, decimals))


def _collect_outputs(currentsimfolder, zonename, voutput, crs_wkt):
    """Renames LISFLOOD-FP's ASCII outputs and converts them to rasters.
    Returns True if steady state was reached (a "-9999.elev" file was
    produced), False if LISFLOOD-FP stopped at max sim_time instead
    ("-0001.elev")."""
    elev_txt = os.path.join(currentsimfolder, f"{zonename}elev.txt")
    if os.path.exists(elev_txt):
        os.remove(elev_txt)

    steady_elev = os.path.join(currentsimfolder, f"{zonename}-9999.elev")
    if os.path.exists(steady_elev):
        os.rename(steady_elev, elev_txt)
        steady = True
    else:
        os.rename(os.path.join(currentsimfolder, f"{zonename}-0001.elev"), elev_txt)
        steady = False

    if voutput:
        vx_txt = os.path.join(currentsimfolder, f"{zonename}Vx.txt")
        vy_txt = os.path.join(currentsimfolder, f"{zonename}Vy.txt")
        for p in (vx_txt, vy_txt):
            if os.path.exists(p):
                os.remove(p)

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