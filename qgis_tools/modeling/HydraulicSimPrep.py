import os

from osgeo import gdal
from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsVectorLayer,
    QgsFields,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsWkbTypes,
    QgsVectorFileWriter,
    QgsCoordinateTransformContext,
)
from qgis.PyQt.QtCore import QVariant


class HydraulicSimPrep(QgsProcessingAlgorithm):

    FLOWDIR       = "FLOWDIR"
    FLOWACC       = "FLOWACC"
    ZONES_FOLDER  = "ZONES_FOLDER"
    DEM           = "DEM"
    WIDTH         = "WIDTH"
    ZBED          = "ZBED"
    MANNING       = "MANNING"
    MASK          = "MASK"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"

    def name(self):
        return "hydraulicsimprep"

    def displayName(self):
        return "Hydraulic simulation preparation"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Modeling"

    def groupId(self):
        return "concordiariverlab_floodtools_modeling"

    def createInstance(self):
        return HydraulicSimPrep()

    def shortHelpString(self):
        return (
            "Hydraulic simulation preparation\n\n"
            "Creates LISFLOOD-FP input files for each tile: clips the DEM to each "
            "zone's bounding-box envelope, traces the flow path from each zone's "
            "source point to find the exit point and detect lateral inflow points, "
            "writes a .bci boundary condition file per zone, and clips width, bed "
            "elevation, Manning's n, and channel mask rasters to ASCII for LISFLOOD.\n\n"
            "Inputs:\n"
            "- Flow direction: watershed-scale D8 flow direction raster (e.g. Lisflood_inputs\\lidar10m_fd)\n"
            "- Flow accumulation: watershed-scale flow accumulation raster (g.g. Lisflood_inputs\\lidar10m_facc)\n"
            "- Tiles folder: folder containing polyzones.gpkg and sourcepoints.gpkg "
            "(from the Tiling tool); zone{N}.tif rasters are also written here\n"
            "- DEM: watershed-scale DEM (e.g. lidar10m_avg)\n"
            "- D4 width, D4 bed elevation, floodplain Manning's n, channel mask: (e.g. Lisflood_inputs\\widthD4, bed, n_floodplain, mask)"
            "rasters clipped per zone and converted to ASCII\n"
            "- Output folder: destination for .bci and ASCII files (Simulations\\sims)\n\n"
            "NB: for small tiles, check the resulting .bci files — the exit window "
            "may incorrectly extend onto the upstream side of the reach.\n"
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessingParameterRasterLayer,
            QgsProcessingParameterFile,
            QgsProcessingParameterNumber,
            QgsProcessingParameterFolderDestination,
        )

        self.addParameter(QgsProcessingParameterRasterLayer(
            self.FLOWDIR, "Flow direction (lidar10m_fd)",
        ))
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.FLOWACC, "Flow accumulation (lidar10m_facc)",
        ))
        self.addParameter(QgsProcessingParameterFile(
            self.ZONES_FOLDER, r"Tiles folder (polyzones.gpkg, sourcepoints.gpkg) (Tiles\)",
            behavior=QgsProcessingParameterFile.Folder,
        ))
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.DEM, "DEM (lidar10m_avg)",
        ))
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.WIDTH, "D4 width (widthD4)",
        ))
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.ZBED, "D4 bed elevation (bed)",
        ))
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.MANNING, "Floodplain Manning's n (n_floodplain)",
        ))
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.MASK, "Channel mask (mask)",
        ))
        self.addParameter(QgsProcessingParameterFolderDestination(
            self.OUTPUT_FOLDER, r"Output folder for .bci and ASCII files (Simulations\sims)",
        ))

    def processAlgorithm(self, parameters, context, feedback):
        flowdir       = self.parameterAsRasterLayer(parameters, self.FLOWDIR, context)
        flowacc       = self.parameterAsRasterLayer(parameters, self.FLOWACC, context)
        zones_folder  = self.parameterAsFile(parameters, self.ZONES_FOLDER, context)
        dem           = self.parameterAsRasterLayer(parameters, self.DEM, context)
        width         = self.parameterAsRasterLayer(parameters, self.WIDTH, context)
        zbed          = self.parameterAsRasterLayer(parameters, self.ZBED, context)
        manning       = self.parameterAsRasterLayer(parameters, self.MANNING, context)
        mask          = self.parameterAsRasterLayer(parameters, self.MASK, context)
        distoutput = 4000  # boundary condition exit window width (m)
        percent = 1.0  # drainage area variation threshold (%) for lateral inflow detection
        output_folder = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)

        if not all([flowdir, flowacc, dem, width, zbed, manning, mask]):
            raise QgsProcessingException("One or more input rasters are invalid")
        if not zones_folder or not os.path.isdir(zones_folder):
            raise QgsProcessingException("Tiles folder is invalid")

        os.makedirs(output_folder, exist_ok=True)

        prepare_hydraulic_sim(
            flowdir_path=flowdir.source(),
            flowacc_path=flowacc.source(),
            zones_folder=zones_folder,
            dem_path=dem.source(),
            width_path=width.source(),
            zbed_path=zbed.source(),
            manning_path=manning.source(),
            mask_path=mask.source(),
            distoutput=distoutput,
            percent=percent,
            output_folder=output_folder,
            crs=flowdir.crs(),
            feedback=feedback,
        )

        return {self.OUTPUT_FOLDER: output_folder}


# =============================================================================
# Core logic
# =============================================================================

D8_STEPS = {
    1:   (0, 1),
    2:   (1, 1),
    4:   (1, 0),
    8:   (1, -1),
    16:  (0, -1),
    32:  (-1, -1),
    64:  (-1, 0),
    128: (-1, 1),
}
VALID_DIRS = set(D8_STEPS.keys())


def _xy_to_rowcol(gt, x, y):
    col = int((x - gt[0]) / gt[1])
    row = int((y - gt[3]) / gt[5])
    return row, col


def _rowcol_to_xy(gt, row, col):
    x = gt[0] + (col + 0.5) * gt[1]
    y = gt[3] + (row + 0.5) * gt[5]
    return x, y


def _load_raster(path):
    ds = gdal.Open(path)
    if ds is None:
        raise QgsProcessingException(f"Could not open raster: {path}")
    gt = ds.GetGeoTransform()
    band = ds.GetRasterBand(1)
    nodata = band.GetNoDataValue()
    array = band.ReadAsArray()
    return gt, array, nodata


def _in_bounds(row, col, array):
    return 0 <= row < array.shape[0] and 0 <= col < array.shape[1]


def _check_raster_match(gt_a, array_a, gt_b, array_b, name_a, name_b, tol=1e-6):
    """Raise if two rasters don't share cell size and pixel grid alignment."""
    px_w_a, px_h_a = abs(gt_a[1]), abs(gt_a[5])
    px_w_b, px_h_b = abs(gt_b[1]), abs(gt_b[5])
    if abs(px_w_a - px_w_b) > tol or abs(px_h_a - px_h_b) > tol:
        raise QgsProcessingException(
            f"{name_a} and {name_b} have different cell sizes: "
            f"{px_w_a}x{px_h_a} vs {px_w_b}x{px_h_b}"
        )
    dx = (gt_a[0] - gt_b[0]) / px_w_a
    dy = (gt_a[3] - gt_b[3]) / px_h_a
    if abs(dx - round(dx)) > tol or abs(dy - round(dy)) > tol:
        raise QgsProcessingException(
            f"{name_a} and {name_b} are not aligned to the same pixel grid"
        )


def _clip_to_extent(input_path, extent, output_path, nodata=-9999):
    """extent: (xmin, ymin, xmax, ymax)"""
    src_ds = gdal.Open(input_path)
    src_gt = src_ds.GetGeoTransform()
    x_res, y_res = abs(src_gt[1]), abs(src_gt[5])
    src_ds = None

    gdal.Warp(
        output_path, input_path,
        outputBounds=extent,
        xRes=x_res, yRes=y_res,
        targetAlignedPixels=True,
        dstNodata=nodata,
        format="GTiff",
    )


def _convert_to_ascii(input_path, output_path):
    gdal.Translate(output_path, input_path, format="AAIGrid")


class _Point:
    __slots__ = ("type", "frompointid", "x", "y", "numzone", "flowacc",
                 "side", "lim1", "lim2", "side2", "lim3", "lim4")


def prepare_hydraulic_sim(
    flowdir_path,
    flowacc_path,
    zones_folder,
    dem_path,
    width_path,
    zbed_path,
    manning_path,
    mask_path,
    distoutput,
    percent,
    output_folder,
    crs,
    feedback=None,
):
    """
    Mirrors ArcGIS execute_DefBCI(): builds per-zone LISFLOOD-FP input files.

    Args:
        flowdir_path   : str — path to watershed-scale D8 flow direction raster
        flowacc_path   : str — path to watershed-scale flow accumulation raster
        zones_folder   : str — folder with polyzones.gpkg / sourcepoints.gpkg;
                         zone{N}.tif rasters are also written here
        dem_path       : str — path to watershed DEM
        width_path     : str — path to D4 width raster
        zbed_path      : str — path to D4 bed elevation raster
        manning_path   : str — path to floodplain Manning's n raster
        mask_path      : str — path to channel mask raster
        distoutput     : int — total exit window width (m)
        percent        : float — flow accumulation increase threshold (%)
        output_folder  : str — destination folder for .bci and ASCII files
        crs            : QgsCoordinateReferenceSystem — CRS for inbci/outbci QC layers
        feedback       : QgsProcessingFeedback or None
    """

    def info(msg):
        if feedback:
            feedback.pushInfo(msg)

    def warn(msg):
        if feedback:
            feedback.pushWarning(msg)
        else:
            print(f"WARNING: {msg}")

    info("Loading flow direction and flow accumulation rasters…")
    fd_gt, fd_array, fd_nodata = _load_raster(flowdir_path)
    fa_gt, fa_array, fa_nodata = _load_raster(flowacc_path)
    dem_gt, dem_array, dem_nodata = _load_raster(dem_path)
    _check_raster_match(fd_gt, fd_array, fa_gt, fa_array, "Flow direction", "Flow accumulation")
    _check_raster_match(fd_gt, fd_array, dem_gt, dem_array, "Flow direction", "DEM")

    polyzones_path    = os.path.join(zones_folder, "polyzones.gpkg")
    sourcepoints_path = os.path.join(zones_folder, "sourcepoints.gpkg")

    polyzones    = QgsVectorLayer(polyzones_path, "polyzones", "ogr")
    sourcepoints = QgsVectorLayer(sourcepoints_path, "sourcepoints", "ogr")

    if not polyzones.isValid():
        raise QgsProcessingException(f"Could not load polyzones from {polyzones_path}")
    if not sourcepoints.isValid():
        raise QgsProcessingException(f"Could not load sourcepoints from {sourcepoints_path}")

    # ------------------------------------------------------------------
    # Step 1: clip DEM to each zone's bounding-box envelope
    # ------------------------------------------------------------------
    info("Step 1/4: Clipping DEM to zone envelopes…")
    zone_extents = {}  # zone_id -> (xmin, ymin, xmax, ymax)

    envelopezones_path = os.path.join(zones_folder, "envelopezones.gpkg")
    envelopezones_fields = QgsFields()
    envelopezones_fields.append(QgsField("GRID_CODE", QVariant.Int))

    envelopezones_options = QgsVectorFileWriter.SaveVectorOptions()
    envelopezones_options.driverName = "GPKG"
    envelopezones_options.fileEncoding = "UTF-8"

    envelopezones_writer = QgsVectorFileWriter.create(
        envelopezones_path,
        envelopezones_fields,
        QgsWkbTypes.Polygon,
        crs,
        QgsCoordinateTransformContext(),
        envelopezones_options,
    )
    if envelopezones_writer is None:
        raise QgsProcessingException(f"Could not create {envelopezones_path}")

    for feat in polyzones.getFeatures():
        if feedback and feedback.isCanceled():
            break
        zone_id = int(feat["GRID_CODE"])
        ext = feat.geometry().boundingBox()
        extent = (ext.xMinimum(), ext.yMinimum(), ext.xMaximum(), ext.yMaximum())
        zone_extents[zone_id] = extent
        _clip_to_extent(dem_path, extent, os.path.join(zones_folder, f"zone{zone_id}.tif"))

        env_feat = QgsFeature(envelopezones_fields)
        env_feat.setGeometry(QgsGeometry.fromRect(ext))
        env_feat.setAttributes([zone_id])
        envelopezones_writer.addFeature(env_feat)

    del envelopezones_writer
    info(f"  Wrote {envelopezones_path}")
    info(f"  {len(zone_extents)} zone(s) clipped")

    # ------------------------------------------------------------------
    # Step 2: trace flow paths from each source point
    # ------------------------------------------------------------------
    info("Step 2/4: Tracing flow paths from source points…")

    input_points  = []  # _Point, type='main' or 'lateral'
    output_points = []  # _Point, zone exit point

    for feat in sourcepoints.getFeatures():
        if feedback and feedback.isCanceled():
            break

        pt = feat.geometry().asPoint()
        zone_id = int(feat["ZoneID"])
        fpid    = int(feat["fpid"])

        main_pt = _Point()
        main_pt.type = "main"
        main_pt.frompointid = fpid
        main_pt.x, main_pt.y = pt.x(), pt.y()
        main_pt.numzone = zone_id

        row, col = _xy_to_rowcol(fa_gt, main_pt.x, main_pt.y)
        if not _in_bounds(row, col, fa_array):
            warn(f"Source point fpid={fpid} (zone {zone_id}) is outside flow accumulation raster")
            continue

        main_pt.flowacc = float(fa_array[row, col])
        input_points.append(main_pt)

        zone_tif = os.path.join(zones_folder, f"zone{zone_id}.tif")
        local_gt, local_array, local_nodata = _load_raster(zone_tif)

        current_row, current_col = _xy_to_rowcol(fd_gt, main_pt.x, main_pt.y)
        local_row, local_col = _xy_to_rowcol(local_gt, main_pt.x, main_pt.y)

        last_flowacc = main_pt.flowacc
        in_raster = True
        prev_row, prev_col = current_row, current_col

        while in_raster:
            prev_row, prev_col = current_row, current_col
            current_flowacc = float(fa_array[current_row, current_col])

            if last_flowacc > 0 and 100.0 * (current_flowacc - last_flowacc) / last_flowacc >= percent:
                lat_pt = _Point()
                lat_pt.type = "lateral"
                lat_pt.frompointid = fpid
                lat_pt.x, lat_pt.y = _rowcol_to_xy(fd_gt, current_row, current_col)
                lat_pt.numzone = zone_id
                lat_pt.flowacc = current_flowacc
                input_points.append(lat_pt)
                last_flowacc = current_flowacc

            direction = int(fd_array[current_row, current_col])
            if direction not in VALID_DIRS:
                in_raster = False
                break

            d_row, d_col = D8_STEPS[direction]
            current_row += d_row
            current_col += d_col
            local_row += d_row
            local_col += d_col

            if not _in_bounds(current_row, current_col, fd_array):
                in_raster = False
            elif int(fd_array[current_row, current_col]) not in VALID_DIRS:
                in_raster = False

            if not _in_bounds(local_row, local_col, local_array):
                in_raster = False
            elif local_nodata is not None and local_array[local_row, local_col] == local_nodata:
                in_raster = False

        out_pt = _Point()
        out_pt.numzone = zone_id
        out_pt.x, out_pt.y = _rowcol_to_xy(fd_gt, prev_row, prev_col)

        xmin, ymin, xmax, ymax = zone_extents[zone_id]
        dist_w, dist_e = out_pt.x - xmin, xmax - out_pt.x
        dist_s, dist_n = out_pt.y - ymin, ymax - out_pt.y
        dist_side = min(dist_w, dist_e, dist_s, dist_n)

        if dist_side == dist_w:
            out_pt.side = "W"
        elif dist_side == dist_e:
            out_pt.side = "E"
        elif dist_side == dist_s:
            out_pt.side = "S"
        else:
            out_pt.side = "N"

        output_points.append(out_pt)

    info(f"  {len(input_points)} input point(s) traced "
         f"({sum(1 for p in input_points if p.type == 'main')} main, "
         f"{sum(1 for p in input_points if p.type == 'lateral')} lateral)")
    info(f"  {len(output_points)} output point(s) found")

    # ------------------------------------------------------------------
    # Step 3: configure boundary condition exit windows
    # ------------------------------------------------------------------
    info("Step 3/4: Configuring boundary condition windows…")

    for pt in output_points:
        zone_tif = os.path.join(zones_folder, f"zone{pt.numzone}.tif")
        gt, array, nodata = _load_raster(zone_tif)
        px_w, px_h = abs(gt[1]), abs(gt[5])
        half_width = distoutput / 2.0

        pt.side2 = "0"
        pt.lim3 = 0
        pt.lim4 = 0

        def walk(x0, y0, row_inc, col_inc, dist_inc):
            row, col = _xy_to_rowcol(gt, x0, y0)
            distance = 0.0
            while (_in_bounds(row, col, array) and array[row, col] != nodata
                   and distance < half_width):
                distance += dist_inc
                row += row_inc
                col += col_inc
            row -= row_inc
            col -= col_inc
            return row, col, distance

        # First direction along the exit edge
        if pt.side in ("W", "E"):
            row_inc, col_inc, dist_inc = 1, 0, px_h
        else:
            row_inc, col_inc, dist_inc = 0, 1, px_w

        row, col, distance = walk(pt.x, pt.y, row_inc, col_inc, dist_inc)
        x1, y1 = _rowcol_to_xy(gt, row, col)
        pt.lim1 = y1 if pt.side in ("W", "E") else x1

        if distance < half_width:
            if pt.side == "W":
                row_inc2, col_inc2, dist_inc2 = 0, 1, px_w
            elif pt.side == "E":
                row_inc2, col_inc2, dist_inc2 = 0, -1, px_w
            elif pt.side == "N":
                row_inc2, col_inc2, dist_inc2 = 1, 0, px_h
            else:
                row_inc2, col_inc2, dist_inc2 = -1, 0, px_h

            row2, col2, _ = walk(x1, y1, row_inc2, col_inc2, dist_inc2)
            x2, y2 = _rowcol_to_xy(gt, row2, col2)
            pt.lim3 = x1 if pt.side in ("W", "E") else y1

            if pt.side in ("W", "E"):
                pt.side2, pt.lim4 = "S", x2
            else:
                pt.side2, pt.lim4 = "E", y2

        # Opposite direction along the exit edge
        if pt.side in ("W", "E"):
            row_inc, col_inc, dist_inc = -1, 0, px_h
        else:
            row_inc, col_inc, dist_inc = 0, -1, px_w

        row, col, distance = walk(pt.x, pt.y, row_inc, col_inc, dist_inc)
        x1b, y1b = _rowcol_to_xy(gt, row, col)
        pt.lim2 = y1b if pt.side in ("W", "E") else x1b

        if distance < half_width and pt.side2 == "0":
            if pt.side == "W":
                row_inc2, col_inc2, dist_inc2 = 0, 1, px_w
            elif pt.side == "E":
                row_inc2, col_inc2, dist_inc2 = 0, -1, px_w
            elif pt.side == "N":
                row_inc2, col_inc2, dist_inc2 = 1, 0, px_h
            else:
                row_inc2, col_inc2, dist_inc2 = -1, 0, px_h

            row2, col2, _ = walk(x1b, y1b, row_inc2, col_inc2, dist_inc2)
            x2b, y2b = _rowcol_to_xy(gt, row2, col2)

            if pt.side in ("W", "E"):
                pt.side2, pt.lim4 = "N", x2b
            else:
                pt.side2, pt.lim4 = "W", y2b

    # ------------------------------------------------------------------
    # Step 3b: write inbci/outbci vector layers for QC
    # ------------------------------------------------------------------
    info("Writing inbci/outbci QC layers…")
    inbci_path = os.path.join(zones_folder, "inbci.gpkg")
    inbci_fields = QgsFields()
    inbci_fields.append(QgsField("zoneid", QVariant.Int))
    inbci_fields.append(QgsField("flowacc", QVariant.Double))
    inbci_fields.append(QgsField("type", QVariant.String))
    inbci_fields.append(QgsField("fpid", QVariant.Int))
    inbci_options = QgsVectorFileWriter.SaveVectorOptions()
    inbci_options.driverName = "GPKG"
    inbci_options.fileEncoding = "UTF-8"
    writer = QgsVectorFileWriter.create(
        inbci_path,
        inbci_fields,
        QgsWkbTypes.Point,
        crs,
        QgsCoordinateTransformContext(),
        inbci_options,
    )
    if writer is None:
        raise QgsProcessingException(f"Could not create {inbci_path}")
    for pt in input_points:
        f = QgsFeature(inbci_fields)
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(pt.x, pt.y)))
        f.setAttributes([pt.numzone, pt.flowacc, pt.type, pt.frompointid])
        writer.addFeature(f)
    del writer

    outbci_path = os.path.join(zones_folder, "outbci.gpkg")
    outbci_fields = QgsFields()
    outbci_fields.append(QgsField("zoneid", QVariant.Int))
    outbci_fields.append(QgsField("side", QVariant.String))
    outbci_fields.append(QgsField("lim1", QVariant.Double))
    outbci_fields.append(QgsField("lim2", QVariant.Double))
    outbci_fields.append(QgsField("side2", QVariant.String))
    outbci_fields.append(QgsField("lim3", QVariant.Double))
    outbci_fields.append(QgsField("lim4", QVariant.Double))
    outbci_options = QgsVectorFileWriter.SaveVectorOptions()
    outbci_options.driverName = "GPKG"
    outbci_options.fileEncoding = "UTF-8"
    writer = QgsVectorFileWriter.create(
        outbci_path,
        outbci_fields,
        QgsWkbTypes.Point,
        crs,
        QgsCoordinateTransformContext(),
        outbci_options,
    )
    if writer is None:
        raise QgsProcessingException(f"Could not create {outbci_path}")
    for pt in output_points:
        f = QgsFeature(outbci_fields)
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(pt.x, pt.y)))
        f.setAttributes([pt.numzone, pt.side, pt.lim1, pt.lim2,
                         pt.side2, pt.lim3, pt.lim4])
        writer.addFeature(f)
    del writer
    info(f"  Wrote {inbci_path} and {outbci_path}")

    # ------------------------------------------------------------------
    # Step 4: write .bci files and ASCII rasters
    # ------------------------------------------------------------------
    info("Step 4/4: Writing .bci files and ASCII rasters…")

    points_by_zone = {}
    for pt in input_points:
        points_by_zone.setdefault(pt.numzone, []).append(pt)

    for zone_id, pts in points_by_zone.items():
        bci_path = os.path.join(output_folder, f"zone{zone_id}.bci")
        latnum = 0
        with open(bci_path, "w") as f:
            for pt in sorted(pts, key=lambda p: p.flowacc):
                if pt.type == "main":
                    f.write(f"P\t{int(pt.x)}\t{int(pt.y)}\tQVAR\tzone{zone_id}\n")
                else:
                    latnum += 1
                    f.write(f"P\t{int(pt.x)}\t{int(pt.y)}\tQVAR\tzone{zone_id}_{latnum}\n")

        out_pt = next((p for p in output_points if p.numzone == zone_id), None)
        if out_pt is not None:
            with open(bci_path, "a") as f:
                f.write(f"{out_pt.side}\t{int(out_pt.lim1)}\t{int(out_pt.lim2)}\tHVAR\thvar")
                if out_pt.side2 != "0":
                    f.write(f"\n{out_pt.side2}\t{int(out_pt.lim3)}\t{int(out_pt.lim4)}\tHVAR\thvar")

    for zone_id, extent in zone_extents.items():
        zone_tif = os.path.join(zones_folder, f"zone{zone_id}.tif")
        _convert_to_ascii(zone_tif, os.path.join(output_folder, f"zone{zone_id}.txt"))

        w_tif = os.path.join(zones_folder, f"wzone{zone_id}.tif")
        d_tif = os.path.join(zones_folder, f"dzone{zone_id}.tif")
        n_tif = os.path.join(zones_folder, f"nzone{zone_id}.tif")
        m_tif = os.path.join(zones_folder, f"mzone{zone_id}.tif")

        _clip_to_extent(width_path, extent, w_tif)
        _clip_to_extent(zbed_path, extent, d_tif)
        _clip_to_extent(manning_path, extent, n_tif)
        _clip_to_extent(mask_path, extent, m_tif)

        _convert_to_ascii(w_tif, os.path.join(output_folder, f"wzone{zone_id}.txt"))
        _convert_to_ascii(d_tif, os.path.join(output_folder, f"dzone{zone_id}.txt"))
        _convert_to_ascii(n_tif, os.path.join(output_folder, f"nzone{zone_id}.txt"))
        _convert_to_ascii(m_tif, os.path.join(output_folder, f"mzone{zone_id}.txt"))

        for tmp in (w_tif, d_tif, n_tif, m_tif):
            if os.path.exists(tmp):
                os.remove(tmp)

    info("Done.")