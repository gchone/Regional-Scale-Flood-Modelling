import math
import numpy as np
from osgeo import gdal

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterRasterDestination,
    QgsProcessing,
    QgsRasterLayer,
)

# =============================================================================
# QgsProcessingAlgorithm
# =============================================================================

class D4FlowDirection(QgsProcessingAlgorithm):

    FLOWDIR   = "FLOWDIR"
    DEM       = "DEM"
    FROMPOINT = "FROMPOINT"
    OUTPUT    = "OUTPUT"

    def name(self):
        return "d4flowdirection"

    def displayName(self):
        return "D4 flow direction"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Modeling"

    def groupId(self):
        return "concordiariverlab_floodtools_modeling"

    def createInstance(self):
        return D4FlowDirection()

    def shortHelpString(self):
        return (
            "D4 flow direction\n\n"
            "Converts a D8 flow direction raster into a D4 flow direction raster "
            "along the flow path from a set of from-points. Diagonal D8 moves "
            "(2, 8, 32, 128) are replaced by two cardinal steps, choosing the "
            "adjacent cell with the lower DEM elevation. Used to prepare flow "
            "direction input for LISFLOOD-FP, which requires D4 paths.\n\n"
            "Inputs:\n"
            "- Flow direction: D8 flow direction raster with values 1/2/4/8/16/32/64/128 (e.g. lidar10m_fd)\n"
            "- DEM: filled DEM raster (e.g. lidar10m_fill)\n"
            "- From points: headwater from-points (e.g. from_pts)\n\n"
            "Output:\n"
            "- D4 flow direction raster (d4fd)"
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessingParameterRasterLayer,
            QgsProcessingParameterFeatureSource,
            QgsProcessingParameterRasterDestination,
            QgsProcessing,
        )
        self.addParameter(QgsProcessingParameterRasterLayer(self.FLOWDIR, "lidar10m_fd"))
        self.addParameter(QgsProcessingParameterRasterLayer(self.DEM, "lidar10m_fill"))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.FROMPOINT, "from_pts", [QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterRasterDestination(self.OUTPUT, "D4 flow direction (d4fd)"))

    def processAlgorithm(self, parameters, context, feedback):
        from qgis.core import QgsProcessingParameterRasterLayer, QgsProcessingUtils

        flowdir_layer = self.parameterAsRasterLayer(parameters, self.FLOWDIR, context)
        dem_layer     = self.parameterAsRasterLayer(parameters, self.DEM, context)
        frompoint_source = self.parameterAsSource(parameters, self.FROMPOINT, context)
        output_path   = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)

        execute_d8tod4(flowdir_layer, dem_layer, frompoint_source, output_path, feedback)

        return {self.OUTPUT: output_path}


# =============================================================================
# Core logic
# =============================================================================

class _FrompointPaths:
    """Tracks which cells have already been visited and by which from-point."""

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


def execute_d8tod4(flowdir_layer, dem_layer, frompoint_source, output_path, feedback):

    # ------------------------------------------------------------------
    # Load rasters via GDAL
    # ------------------------------------------------------------------
    fd_ds  = gdal.Open(flowdir_layer.source())
    dem_ds = gdal.Open(dem_layer.source())

    fd_band  = fd_ds.GetRasterBand(1)
    dem_band = dem_ds.GetRasterBand(1)

    fd_array  = fd_band.ReadAsArray().astype(float)
    dem_array = dem_band.ReadAsArray().astype(float)

    fd_nodata  = fd_band.GetNoDataValue()
    dem_nodata = dem_band.GetNoDataValue()

    gt     = fd_ds.GetGeoTransform()   # (originX, pixelW, 0, originY, 0, pixelH)
    n_rows = fd_ds.RasterYSize
    n_cols = fd_ds.RasterXSize

    origin_x = gt[0]
    pixel_w  = gt[1]
    origin_y = gt[3]
    pixel_h  = gt[5]   # negative for north-up rasters

    def x_to_col(x):
        return int(math.floor((x - origin_x) / pixel_w))

    def y_to_row(y):
        return int(math.floor((y - origin_y) / pixel_h))

    def get_fd(row, col):
        if row < 0 or row >= n_rows or col < 0 or col >= n_cols:
            return None
        v = fd_array[row, col]
        if fd_nodata is not None and v == fd_nodata:
            return None
        return int(v)

    def get_dem(row, col):
        if row < 0 or row >= n_rows or col < 0 or col >= n_cols:
            return None
        v = dem_array[row, col]
        if dem_nodata is not None and v == dem_nodata:
            return None
        return float(v)

    VALID_FD = {1, 2, 4, 8, 16, 32, 64, 128}

    # ------------------------------------------------------------------
    # Output array — initialised to NoData (-9999)
    # ------------------------------------------------------------------
    result = np.full((n_rows, n_cols), -9999.0, dtype=float)

    donepoints = _FrompointPaths()

    # ------------------------------------------------------------------
    # Iterate over from-points
    # ------------------------------------------------------------------
    features = list(frompoint_source.getFeatures())
    total = len(features)

    for i, feat in enumerate(features):
        if feedback.isCanceled():
            break

        feedback.setProgress(int(i / total * 100))

        pt     = feat.geometry().asPoint()
        fp_id  = feat.id()

        current_col = x_to_col(pt.x())
        current_row = y_to_row(pt.y())

        # Safety check: from-point must be inside raster with a valid fd value
        in_raster = True
        if current_col < 0 or current_col >= n_cols or current_row < 0 or current_row >= n_rows:
            in_raster = False
        elif get_fd(current_row, current_col) not in VALID_FD:
            in_raster = False

        while in_raster:
            direction = get_fd(current_row, current_col)
            donepoints.add_point(current_row, current_col, fp_id)

            # Cardinal directions — write value and step
            if direction == 1:
                result[current_row, current_col] = direction
                current_col += 1

            elif direction == 4:
                result[current_row, current_col] = direction
                current_row += 1

            elif direction == 16:
                result[current_row, current_col] = direction
                current_col -= 1

            elif direction == 64:
                result[current_row, current_col] = direction
                current_row -= 1

            # Diagonal directions — split into two cardinal steps via lower neighbour
            elif direction == 2:   # diagonal: row+1, col+1
                elev_right = get_dem(current_row,     current_col + 1)
                elev_down  = get_dem(current_row + 1, current_col)
                if elev_right is None:
                    result[current_row, current_col] = 1
                    in_raster = False
                elif elev_down is None:
                    result[current_row, current_col] = 4
                    in_raster = False
                elif elev_right < elev_down:
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
                current_col += 1
                current_row += 1

            elif direction == 8:   # diagonal: row+1, col-1
                elev_down = get_dem(current_row + 1, current_col)
                elev_left = get_dem(current_row,     current_col - 1)
                if elev_down is None:
                    result[current_row, current_col] = 4
                    in_raster = False
                elif elev_left is None:
                    result[current_row, current_col] = 16
                    in_raster = False
                elif elev_down < elev_left:
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
                current_col -= 1
                current_row += 1

            elif direction == 32:  # diagonal: row-1, col-1
                elev_up   = get_dem(current_row - 1, current_col)
                elev_left = get_dem(current_row,     current_col - 1)
                if elev_up is None:
                    result[current_row, current_col] = 64
                    in_raster = False
                elif elev_left is None:
                    result[current_row, current_col] = 16
                    in_raster = False
                elif elev_up < elev_left:
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
                current_col -= 1
                current_row -= 1

            elif direction == 128: # diagonal: row-1, col+1
                elev_up    = get_dem(current_row - 1, current_col)
                elev_right = get_dem(current_row,     current_col + 1)
                if elev_up is None:
                    result[current_row, current_col] = 64
                    in_raster = False
                elif elev_right is None:
                    result[current_row, current_col] = 1
                    in_raster = False
                elif elev_up < elev_right:
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
                current_col += 1
                current_row -= 1

            # Bounds and validity check for next cell
            if in_raster:
                if current_col < 0 or current_col >= n_cols or current_row < 0 or current_row >= n_rows:
                    in_raster = False
                elif get_fd(current_row, current_col) not in VALID_FD:
                    in_raster = False
                elif donepoints.done_previously(current_row, current_col, fp_id):
                    in_raster = False

    # ------------------------------------------------------------------
    # Write output raster
    # ------------------------------------------------------------------
    driver = gdal.GetDriverByName("GTiff")
    out_ds = driver.Create(output_path, n_cols, n_rows, 1, gdal.GDT_Float32)
    out_ds.SetGeoTransform(gt)
    out_ds.SetProjection(fd_ds.GetProjection())
    out_band = out_ds.GetRasterBand(1)
    out_band.SetNoDataValue(-9999.0)
    out_band.WriteArray(result)
    out_band.FlushCache()
    out_ds = None
    fd_ds  = None
    dem_ds = None

    feedback.pushInfo("D4 flow direction complete.")