import math
import os
import numpy as np
from osgeo import gdal

import processing
from qgis.core import (
    QgsProject,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessing,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterNumber,
    QgsProcessingParameterFolderDestination,
    QgsFeature,
    QgsFields,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsRectangle,
    QgsVectorLayer,
    QgsVectorFileWriter,
    QgsCoordinateTransformContext,
    QgsSpatialIndex,
)
from qgis.PyQt.QtCore import QMetaType


# =============================================================================
# QgsProcessingAlgorithm
# =============================================================================

class Tiling(QgsProcessingAlgorithm):

    FLOWDIR    = "FLOWDIR"
    LAKES      = "LAKES"
    FROMPOINT  = "FROMPOINT"
    DISTANCE   = "DISTANCE"
    BUFFERW    = "BUFFERW"
    OUT_FOLDER = "OUT_FOLDER"

    def name(self):
        return "tiling"

    def displayName(self):
        return "Tiling"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Modeling"

    def groupId(self):
        return "concordiariverlab_floodtools_modeling"

    def createInstance(self):
        return Tiling()

    def shortHelpString(self):
        return (
            "Tiling\n\n"
            "Divides the study network into independent tiles for hydraulic simulations "
            "with LISFLOOD-FP. Segments the D8 flow path from each from-point by distance "
            "and lake boundaries. Creates tile polygons (polyzones) as rectangular envelopes "
            "around buffered segments, and source points at the upstream end of each tile.\n\n"
            "Inputs:\n"
            "- Flow direction: D8 flow direction raster (e.g. lidar10m_fd)\n"
            "- Lakes: lake polygon layer used as tile boundaries\n"
            "- From points: headwater from-points (e.g. from_pts)\n"
            "- Tiles length (m): target length of each tile along the flow path (default 15000)\n"
            "- Tiles minimum width (m): buffer distance for tile width (default 3000)\n"
            "- Tiles folder: output folder where polyzones and sourcepoints will be written\n\n"
            "Outputs:\n"
            "- polyzones.gpkg: rectangular tile polygons with GRID_CODE and Lake_ID fields\n"
            "- sourcepoints.gpkg: upstream source point for each tile\n"
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.FLOWDIR, "Flow direction (e.g. lidar10m_fd)"))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.LAKES, "Lakes",
            [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.FROMPOINT, "From points (e.g. from_pts)",
            [QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterNumber(
            self.DISTANCE, "Tiles length (m)",
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=15000))
        self.addParameter(QgsProcessingParameterNumber(
            self.BUFFERW, "Tiles minimum width (m)",
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=3000))
        self.addParameter(QgsProcessingParameterFolderDestination(
            self.OUT_FOLDER, "Tiles folder"))

    def processAlgorithm(self, parameters, context, feedback):
        flowdir_layer = self.parameterAsRasterLayer(parameters, self.FLOWDIR, context)
        lakes_layer   = self.parameterAsVectorLayer(parameters, self.LAKES, context)
        frompt_layer  = self.parameterAsVectorLayer(parameters, self.FROMPOINT, context)
        distance      = self.parameterAsInt(parameters, self.DISTANCE, context)
        bufferw       = self.parameterAsInt(parameters, self.BUFFERW, context)
        out_folder    = self.parameterAsString(parameters, self.OUT_FOLDER, context)

        if flowdir_layer is None:
            raise QgsProcessingException("Flow direction layer is invalid")
        if lakes_layer is None:
            raise QgsProcessingException("Lakes layer is invalid")
        if frompt_layer is None:
            raise QgsProcessingException("From points layer is invalid")

        os.makedirs(out_folder, exist_ok=True)

        execute_create_zones(
            flowdir_layer, lakes_layer, frompt_layer, distance, bufferw, out_folder, feedback
        )

        return {self.OUT_FOLDER: out_folder}


# =============================================================================
# Core logic
# =============================================================================

class _PointFlowPath:
    pass


def execute_create_zones(flowdir_layer, lakes_layer, frompt_layer, distance, bufferw, out_folder, feedback):

    # ------------------------------------------------------------------
    # Load flow direction raster
    # ------------------------------------------------------------------
    fd_ds     = gdal.Open(flowdir_layer.source())
    fd_band   = fd_ds.GetRasterBand(1)
    fd_array  = fd_band.ReadAsArray().astype(float)
    fd_nodata = fd_band.GetNoDataValue()
    gt        = fd_ds.GetGeoTransform()
    proj      = fd_ds.GetProjection()
    n_rows    = fd_ds.RasterYSize
    n_cols    = fd_ds.RasterXSize
    cell_w    = gt[1]
    cell_h    = abs(gt[5])
    origin_x  = gt[0]
    origin_y  = gt[3]
    fd_ds     = None

    VALID_FD = {1, 2, 4, 8, 16, 32, 64, 128}

    def x_to_col(x):
        return int(math.floor((x - origin_x) / cell_w))

    def y_to_row(y):
        return int(math.floor((y - origin_y) / (-cell_h)))

    def col_to_x(col):
        return origin_x + (col + 0.5) * cell_w

    def row_to_y(row):
        return origin_y - (row + 0.5) * cell_h

    def get_fd(row, col):
        if row < 0 or row >= n_rows or col < 0 or col >= n_cols:
            return None
        v = fd_array[row, col]
        if fd_nodata is not None and v == fd_nodata:
            return None
        return int(v)

    # ------------------------------------------------------------------
    # Rasterize lakes (burn value 1 = in lake, -1 = nodata)
    # ------------------------------------------------------------------
    feedback.pushInfo("Rasterizing lakes...")
    tmp_lakes_raster = os.path.join(out_folder, "_tmp_lakes.tif")

    processing.run("gdal:rasterize", {
        'INPUT':   lakes_layer,
        'FIELD':   '',
        'BURN':    1,
        'USE_Z':   False,
        'UNITS':   1,
        'WIDTH':   cell_w,
        'HEIGHT':  cell_h,
        'EXTENT':  f"{origin_x},{origin_x + n_cols * cell_w},{origin_y - n_rows * cell_h},{origin_y} [{flowdir_layer.crs().authid()}]",
        'NODATA':  -1,
        'OPTIONS': '',
        'DATA_TYPE': 5,
        'INIT':    -1,
        'INVERT':  False,
        'EXTRA':   '-tap',
        'OUTPUT':  tmp_lakes_raster,
    })

    lakes_ds    = gdal.Open(tmp_lakes_raster)
    lakes_array = lakes_ds.GetRasterBand(1).ReadAsArray().astype(np.int32)
    lakes_ds    = None

    # Spatial index for fast lake lookup by feature ID
    lakes_index = QgsSpatialIndex(lakes_layer.getFeatures())
    lakes_dict  = {feat.id(): feat for feat in lakes_layer.getFeatures()}

    # Build lake extents dict: lake_fid -> (xmin, xmax, ymin, ymax)
    lake_extents = {}
    for feat in lakes_layer.getFeatures():
        bbox = feat.geometry().boundingBox()
        lake_extents[feat.id()] = (bbox.xMinimum(), bbox.xMaximum(),
                                   bbox.yMinimum(), bbox.yMaximum())

    def get_lake(row, col):
        if row < 0 or row >= n_rows or col < 0 or col >= n_cols:
            return -1
        return int(lakes_array[row, col])

    def get_lake_fid(x, y):
        """Return the feature ID of the lake containing point (x, y), or -1 if none."""
        pt_geom      = QgsGeometry.fromPointXY(QgsPointXY(x, y))
        candidate_ids = lakes_index.intersects(pt_geom.boundingBox())
        for fid in candidate_ids:
            if lakes_dict[fid].geometry().contains(pt_geom):
                return fid
        return -1

    # ------------------------------------------------------------------
    # Segments raster — initialized to -9999
    # ------------------------------------------------------------------
    segments_array = np.full((n_rows, n_cols), -9999, dtype=np.int32)

    segnumber    = 0
    lakes_bci    = {}  # segnumber -> lake fid
    toclip       = {}  # segnumber -> [clip_type, value]
    input_points = {}  # segnumber -> _PointFlowPath

    # ------------------------------------------------------------------
    # Walk flow path from each from-point
    # ------------------------------------------------------------------
    feedback.pushInfo("Segmenting flow paths...")
    from_features = list(frompt_layer.getFeatures())
    total         = len(from_features)

    for fp_idx, frompoint in enumerate(from_features):
        if feedback.isCanceled():
            break
        feedback.setProgress(int(fp_idx / total * 50))

        pt    = frompoint.geometry().asPoint()
        fp_id = frompoint.id()

        segnumber += 1

        current_col = x_to_col(pt.x())
        current_row = y_to_row(pt.y())

        in_raster = True
        if current_col < 0 or current_col >= n_cols or current_row < 0 or current_row >= n_rows:
            in_raster = False
        elif get_fd(current_row, current_col) not in VALID_FD:
            in_raster = False

        listpointsflowpath = []
        totaldistance      = 0
        currentdistance    = 0
        inlake             = False
        dividedriver       = False
        listtomerged       = []

        while in_raster:
            waslake = inlake
            inlake  = False
            lakeval = get_lake(current_row, current_col)
            inlake  = (lakeval == 1)

            if not (inlake and waslake):
                totaldistance += currentdistance

            # Entering a lake
            if inlake and not waslake:
                coord_x  = col_to_x(current_col)
                coord_y  = row_to_y(current_row)
                lake_fid = get_lake_fid(coord_x, coord_y)

                if lake_fid >= 0:
                    lakes_bci[segnumber] = lake_fid
                    xmin, xmax, ymin, ymax = lake_extents.get(lake_fid, (0, 0, 0, 0))

                    if (xmin, xmax, ymin, ymax) != (0, 0, 0, 0):
                        dists = {
                            "Xmax": abs(coord_x - xmin),
                            "Xmin": abs(coord_x - xmax),
                            "Ymax": abs(coord_y - ymin),
                            "Ymin": abs(coord_y - ymax),
                        }
                        clip_type = min(dists, key=dists.get)
                        clip_val  = {"Xmax": xmin, "Xmin": xmax,
                                     "Ymax": ymin, "Ymin": ymax}[clip_type]
                        toclip[segnumber] = [clip_type, clip_val]

                if totaldistance < 0.3 * distance and dividedriver:
                    if segnumber in toclip:
                        toclip[segnumber - 1] = toclip.pop(segnumber)
                    listtomerged.append(segnumber)

                totaldistance = 0
                segnumber    += 1
                dividedriver  = False

            # Exiting a lake
            elif not inlake and waslake:
                cp = _PointFlowPath()
                cp.row = current_row
                cp.col = current_col
                cp.X = col_to_x(current_col)
                cp.Y = row_to_y(current_row)
                cp.distance = 0
                cp.segnumber = segnumber
                cp.frompointid = fp_id
                cp.is_lake_exit = True
                listpointsflowpath.append(cp)
                totaldistance = 0

            elif totaldistance > distance:
                totaldistance = 0
                segnumber    += 1
                dividedriver  = True

            if not inlake and not waslake:
                cp             = _PointFlowPath()
                cp.row         = current_row
                cp.col         = current_col
                cp.X           = col_to_x(current_col)
                cp.Y           = row_to_y(current_row)
                cp.distance    = totaldistance
                cp.segnumber   = segnumber
                cp.frompointid = fp_id
                listpointsflowpath.append(cp)

            # Step along flow direction
            direction = get_fd(current_row, current_col)
            diag_dist = math.sqrt(cell_w ** 2 + cell_h ** 2)

            if direction == 1:
                current_col     += 1
                currentdistance  = cell_w
            if direction == 2:
                current_col     += 1
                current_row     += 1
                currentdistance  = diag_dist
            if direction == 4:
                current_row     += 1
                currentdistance  = cell_h
            if direction == 8:
                current_col     -= 1
                current_row     += 1
                currentdistance  = diag_dist
            if direction == 16:
                current_col     -= 1
                currentdistance  = cell_w
            if direction == 32:
                current_col     -= 1
                current_row     -= 1
                currentdistance  = diag_dist
            if direction == 64:
                current_row     -= 1
                currentdistance  = cell_h
            if direction == 128:
                current_col     += 1
                current_row     -= 1
                currentdistance  = diag_dist

            # Bounds check
            if current_col < 0 or current_col >= n_cols or current_row < 0 or current_row >= n_rows:
                in_raster = False
            elif get_fd(current_row, current_col) not in VALID_FD:
                in_raster = False

            if in_raster:
                confluence_seg = segments_array[current_row, current_col]
                if confluence_seg != -9999:
                    if confluence_seg in listtomerged:
                        confluence_seg -= 1
                    if confluence_seg in toclip:
                        toclip[segnumber] = list(toclip[confluence_seg])
                    if totaldistance < 0.3 * distance and dividedriver:
                        listtomerged.append(segnumber)
                        if segnumber in toclip:
                            toclip[segnumber - 1] = toclip.pop(segnumber)
                    in_raster = False

        # Record points
        for cp in listpointsflowpath:
            if cp.segnumber in listtomerged:
                cp.segnumber -= 1
            segments_array[cp.row, cp.col] = cp.segnumber
            is_lake_exit = getattr(cp, 'is_lake_exit', False)
            if cp.segnumber not in input_points or is_lake_exit:
                newpt             = _PointFlowPath()
                newpt.type        = "main"
                newpt.frompointid = cp.frompointid
                newpt.X           = cp.X
                newpt.Y           = cp.Y
                input_points[cp.segnumber] = newpt

        # Remap lakes_bci keys for any merged segments
        for seg in list(lakes_bci.keys()):
            if seg in listtomerged:
                lakes_bci[seg - 1] = lakes_bci.pop(seg)
        for seg in list(toclip.keys()):
            if seg in listtomerged:
                toclip[seg - 1] = toclip.pop(seg)

    # ------------------------------------------------------------------
    # Write segments raster to temp file
    # ------------------------------------------------------------------
    feedback.pushInfo("Writing segments raster...")
    tmp_segments = os.path.join(out_folder, "_tmp_segments.tif")
    driver  = gdal.GetDriverByName("GTiff")
    seg_ds  = driver.Create(tmp_segments, n_cols, n_rows, 1, gdal.GDT_Int32)
    seg_ds.SetGeoTransform(gt)
    seg_ds.SetProjection(proj)
    seg_band = seg_ds.GetRasterBand(1)
    seg_band.SetNoDataValue(-9999)
    seg_band.WriteArray(segments_array)
    seg_band.FlushCache()
    seg_ds = None

    # ------------------------------------------------------------------
    # Polygonize segments raster -> dissolve by GRID_CODE -> extract boundaries as lines
    # ------------------------------------------------------------------
    feedback.pushInfo("Converting segments raster to lines...")
    tmp_seg_poly = os.path.join(out_folder, "_tmp_seg_poly.gpkg")
    processing.run("gdal:polygonize", {
        'INPUT':               tmp_segments,
        'BAND':                1,
        'FIELD':               'GRID_CODE',
        'EIGHT_CONNECTEDNESS': False,
        'EXTRA':               '',
        'OUTPUT':              tmp_seg_poly,
    })

    tmp_seg_poly_dissolved = os.path.join(out_folder, "_tmp_seg_poly_dissolved.gpkg")
    processing.run("native:dissolve", {
        'INPUT':  tmp_seg_poly,
        'FIELD':  ['GRID_CODE'],
        'OUTPUT': tmp_seg_poly_dissolved,
    })

    tmp_seg_lines = os.path.join(out_folder, "_tmp_seg_lines.gpkg")
    processing.run("native:polygonstolines", {
        'INPUT':  tmp_seg_poly_dissolved,
        'OUTPUT': tmp_seg_lines,
    })

    # ------------------------------------------------------------------
    # GRASS r.grow to create tile buffer zones within bufferw distance
    # ------------------------------------------------------------------
    feedback.pushInfo("Running r.grow to create buffer zones...")
    tmp_regions = os.path.join(out_folder, "_tmp_regions.tif")
    processing.run("grass:r.grow", {
        'input':                          tmp_segments,
        'radius':                         bufferw,
        'metric':                         0,
        '-m':                             True,
        'output':                         tmp_regions,
        'GRASS_REGION_PARAMETER':         None,
        'GRASS_REGION_CELLSIZE_PARAMETER': 0,
        'GRASS_RASTER_FORMAT_OPT':        '',
        'GRASS_RASTER_FORMAT_META':       '',
    })

    # ------------------------------------------------------------------
    # Polygonize r.grow result
    # ------------------------------------------------------------------
    feedback.pushInfo("Polygonizing buffer zones...")
    tmp_euc_poly = os.path.join(out_folder, "_tmp_eucpoly.gpkg")
    processing.run("gdal:polygonize", {
        'INPUT':               tmp_regions,
        'BAND':                1,
        'FIELD':               'GRID_CODE',
        'EIGHT_CONNECTEDNESS': False,
        'EXTRA':               '',
        'OUTPUT':              tmp_euc_poly,
    })

    # ------------------------------------------------------------------
    # Buffer line segments (longitudinal buffer = bufferw/10)
    # ------------------------------------------------------------------
    feedback.pushInfo("Buffering line segments...")
    tmp_line_buf = os.path.join(out_folder, "_tmp_linebuf.gpkg")
    processing.run("native:buffer", {
        'INPUT':         tmp_seg_lines,
        'DISTANCE':      bufferw / 10.0,
        'SEGMENTS':      5,
        'END_CAP_STYLE': 0,
        'JOIN_STYLE':    0,
        'MITER_LIMIT':   2,
        'DISSOLVE':      False,
        'OUTPUT':        tmp_line_buf,
    })

    # ------------------------------------------------------------------
    # Merge buffered lines + euclidean polygons, dissolve, single parts
    # ------------------------------------------------------------------
    feedback.pushInfo("Merging and dissolving buffers...")
    tmp_merged = os.path.join(out_folder, "_tmp_merged.gpkg")
    processing.run("native:mergevectorlayers", {
        'LAYERS': [tmp_line_buf, tmp_euc_poly],
        'CRS':    None,
        'OUTPUT': tmp_merged,
    })

    tmp_buffered_segs = os.path.join(out_folder, "_tmp_buffered_segs.gpkg")
    processing.run("native:dissolve", {
        'INPUT':  tmp_merged,
        'FIELD':  ['GRID_CODE'],
        'OUTPUT': tmp_buffered_segs,
    })

    tmp_buffered_segs_single = os.path.join(out_folder, "_tmp_buffered_segs_single.gpkg")
    processing.run("native:multiparttosingleparts", {
        'INPUT':  tmp_buffered_segs,
        'OUTPUT': tmp_buffered_segs_single,
    })

    # ------------------------------------------------------------------
    # Build polyzones as rectangular envelopes, clipped to lake extents
    # ------------------------------------------------------------------
    feedback.pushInfo("Building polyzones...")

    polyzones_path    = os.path.join(out_folder, "polyzones.gpkg")
    sourcepoints_path = os.path.join(out_folder, "sourcepoints.gpkg")

    poly_layer = QgsVectorLayer(tmp_buffered_segs_single, "buffered_segs", "ogr")

    poly_fields = QgsFields()
    poly_fields.append(QgsField("GRID_CODE", QMetaType.Int))
    poly_fields.append(QgsField("Lake_ID",   QMetaType.Int))

    poly_options                      = QgsVectorFileWriter.SaveVectorOptions()
    poly_options.driverName           = "GPKG"
    poly_options.layerName            = "polyzones"
    poly_options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile

    poly_tmp_lyr = QgsVectorLayer(
        f"Polygon?crs={flowdir_layer.crs().authid()}", "polyzones_tmp", "memory"
    )
    poly_pr = poly_tmp_lyr.dataProvider()
    poly_pr.addAttributes(poly_fields)
    poly_tmp_lyr.updateFields()

    for feat in poly_layer.getFeatures():
        grid_code = feat["GRID_CODE"]
        bbox      = feat.geometry().boundingBox()
        xmin      = bbox.xMinimum()
        ymin      = bbox.yMinimum()
        xmax      = bbox.xMaximum()
        ymax      = bbox.yMaximum()

        if grid_code in toclip:
            clip_type, clip_val = toclip[grid_code]
            if clip_type == "Xmin":
                xmin = max(clip_val, xmin)
            elif clip_type == "Xmax":
                xmax = min(clip_val, xmax)
            elif clip_type == "Ymin":
                ymin = max(clip_val, ymin)
            elif clip_type == "Ymax":
                ymax = min(clip_val, ymax)

        rect_geom = QgsGeometry.fromRect(QgsRectangle(xmin, ymin, xmax, ymax))
        lake_id   = lakes_bci.get(grid_code, -999)

        out_feat = QgsFeature(poly_fields)
        out_feat.setGeometry(rect_geom)
        out_feat["GRID_CODE"] = grid_code
        out_feat["Lake_ID"]   = lake_id
        poly_pr.addFeature(out_feat)

    poly_tmp_lyr.updateExtents()
    QgsVectorFileWriter.writeAsVectorFormatV3(
        poly_tmp_lyr, polyzones_path,
        QgsCoordinateTransformContext(), poly_options
    )
    feedback.pushInfo(f"Saved polyzones to {polyzones_path}")

    # ------------------------------------------------------------------
    # Write sourcepoints
    # ------------------------------------------------------------------
    feedback.pushInfo("Writing sourcepoints...")

    sp_fields = QgsFields()
    sp_fields.append(QgsField("ZoneID", QMetaType.Int))
    sp_fields.append(QgsField("fpid",   QMetaType.Int))

    sp_options                      = QgsVectorFileWriter.SaveVectorOptions()
    sp_options.driverName           = "GPKG"
    sp_options.layerName            = "sourcepoints"
    sp_options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile

    sp_tmp_lyr = QgsVectorLayer(
        f"Point?crs={flowdir_layer.crs().authid()}", "sourcepoints_tmp", "memory"
    )
    sp_pr = sp_tmp_lyr.dataProvider()
    sp_pr.addAttributes(sp_fields)
    sp_tmp_lyr.updateFields()

    for seg_id, pt in input_points.items():
        out_feat = QgsFeature(sp_fields)
        out_feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(pt.X, pt.Y)))
        out_feat["ZoneID"] = seg_id
        out_feat["fpid"]   = pt.frompointid
        sp_pr.addFeature(out_feat)

    sp_tmp_lyr.updateExtents()
    QgsVectorFileWriter.writeAsVectorFormatV3(
        sp_tmp_lyr, sourcepoints_path,
        QgsCoordinateTransformContext(), sp_options
    )
    feedback.pushInfo(f"Saved sourcepoints to {sourcepoints_path}")

    # ------------------------------------------------------------------
    # Load layers in map
    # ------------------------------------------------------------------
    polyzones_lyr = QgsVectorLayer(
        f"{polyzones_path}|layername=polyzones", "polyzones", "ogr")
    sourcepoints_lyr = QgsVectorLayer(
        f"{sourcepoints_path}|layername=sourcepoints", "sourcepoints", "ogr")
    QgsProject.instance().addMapLayer(polyzones_lyr)
    QgsProject.instance().addMapLayer(sourcepoints_lyr)

    # ------------------------------------------------------------------
    # Clean up temp files
    # ------------------------------------------------------------------
    tmp_files = [
        tmp_lakes_raster, tmp_segments, tmp_seg_poly, tmp_seg_poly_dissolved,
        tmp_seg_lines, tmp_regions, tmp_euc_poly, tmp_line_buf,
        tmp_merged, tmp_buffered_segs, tmp_buffered_segs_single,
    ]
    for tmp in tmp_files:
        if tmp is None:
            continue
        for ext in ['', '.shp', '.shx', '.dbf', '.prj', '.cpg']:
            p = tmp if ext == '' else os.path.splitext(tmp)[0] + ext
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

    feedback.pushInfo("Tiling complete.")