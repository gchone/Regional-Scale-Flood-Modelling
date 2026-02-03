import os
import math
import tempfile
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterNumber,
    QgsProcessingParameterEnum,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFolderDestination,
    QgsRasterLayer,
    QgsRectangle
)
import processing


class BatchProcessAggregate_QGIS(QgsProcessingAlgorithm):
    """
    Batch aggregation of raster DEM tiles using GRASS r.resamp.stats.

    This tool reproduces the behavior of the ArcGIS Aggregate tool by:
    - aggregating rasters by an integer factor,
    - aligning all outputs to a common snapped grid defined by the first raster,
    - optionally expanding or truncating the extent,
    - supporting multiple aggregation statistics.
    """

    def name(self):
        return "batch_process_aggregate"

    def displayName(self):
        return "Batch Process Aggregate"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Modeling"

    def groupId(self):
        return "concordiariverlab_floodtools_modeling"

    def createInstance(self):
        return BatchProcessAggregate_QGIS()

    INPUT_RASTERS = "INPUT_RASTERS"
    FACTOR = "FACTOR"
    TECH = "TECH"
    EXPAND = "EXPAND"
    IGNORE_NODATA = "IGNORE_NODATA"
    OUT_DIR = "OUT_DIR"

    def initAlgorithm(self, config=None):
        # Input rasters (multiple)
        self.addParameter(QgsProcessingParameterMultipleLayers(
            self.INPUT_RASTERS,
            "Rasters to aggregate",
            layerType=QgsProcessing.TypeRaster
        ))

        # Aggregation factor
        self.addParameter(QgsProcessingParameterNumber(
            self.FACTOR,
            "Cell factor (integer)",
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=10,
            minValue=1
        ))

        # Aggregation method
        self.addParameter(QgsProcessingParameterEnum(
            self.TECH,
            "Aggregation method",
            options=["average", "median", "mode", "minimum", "maximum"],
            defaultValue=0  # Average
        ))

        # Control whether the output extent is expanded or truncated to fit full blocks
        self.addParameter(QgsProcessingParameterBoolean(
            self.EXPAND,
            "Expand extent if needed",
            defaultValue=True
        ))

        # Control how NoData values are handled during aggregation
        self.addParameter(QgsProcessingParameterBoolean(
            self.IGNORE_NODATA,
            "Ignore NoData in calculations",
            defaultValue=True
        ))

        # Output folder for aggregated rasters
        self.addParameter(QgsProcessingParameterFolderDestination(
            self.OUT_DIR,
            "Output location"
        ))

    def processAlgorithm(self, parameters, context, feedback):

        # Notify user that some GRASS warnings are expected and non-fatal
        feedback.reportError(
            "Note: Non-fatal GRASS warnings may appear on Windows; outputs are still valid.",
            fatalError=False
        )

        # Read and validate user inputs
        rasters = self.parameterAsLayerList(parameters, self.INPUT_RASTERS, context)
        if not rasters:
            raise QgsProcessingException("No rasters provided")

        factor = self.parameterAsInt(parameters, self.FACTOR, context)
        tech_idx = self.parameterAsEnum(parameters, self.TECH, context)
        expand = self.parameterAsBool(parameters, self.EXPAND, context)
        ignore_nodata = self.parameterAsBool(parameters, self.IGNORE_NODATA, context)
        out_dir = self.parameterAsString(parameters, self.OUT_DIR, context)

        # GRASS flag: -n propagates NULLs
        propagate_nulls = not ignore_nodata

        # Define reference grid from the first raster
        ref = rasters[0]
        if not isinstance(ref, QgsRasterLayer):
            raise QgsProcessingException("Reference layer is not a raster")

        # Compute aggregated cell size from reference raster resolution
        cellsize = ref.rasterUnitsPerPixelX() * factor
        snap_ref = None

        # Batch processing loop
        total = len(rasters)

        for i, lyr in enumerate(rasters):
            if feedback.isCanceled():
                break

            # Input raster path and output
            src = lyr.source()
            src_extent = lyr.extent()
            base = os.path.splitext(os.path.basename(src))[0]
            out_path = os.path.join(out_dir, f"{base}_agg.tif")

            feedback.pushInfo(f"Aggregating raster {i+1}/{total}: {base}")

            # Aggregate rasters using GRASS r.resamp.stats
            alg_params = {
                "input": src,
                "method": tech_idx,
                "output": out_path,
                "-n": propagate_nulls,
                "GRASS_REGION_CELLSIZE_PARAMETER": cellsize,
                "GRASS_RASTER_FORMAT_OPT": "",
                "GRASS_RASTER_FORMAT_META": ""
            }

            if i == 0:
                region = snapped_extent(src_extent, cellsize, expand)
                alg_params.update({
                    "GRASS_REGION_EXTENT_PARAMETER": region
                })

                processing.run(
                    "grass7:r.resamp.stats",
                    alg_params,
                    context=context,
                    feedback=None,
                    is_child_algorithm=True
                )

                # Set snap reference ONCE
                snap_ref = QgsRasterLayer(out_path, "snap_ref")
                if not snap_ref.isValid():
                    raise QgsProcessingException("Failed to create snap reference raster")


            else:
                region = snapped_extent_to_snap(src_extent, snap_ref, cellsize, expand)
                alg_params.update({
                    "GRASS_REGION_EXTENT_PARAMETER": region
                })

                processing.run(
                    "grass7:r.resamp.stats",
                    alg_params,
                    context=context,
                    feedback=None,
                    is_child_algorithm=True
                )

            # Update progress bar
            feedback.pushInfo(f"Finished {i+1}/{total}: {base} → {out_path}")
            feedback.setProgress(int((i+1) * 100 / total))

        return {"OUTPUT_FOLDER": out_dir}

    # Help text shown in QGIS Processing toolbox
    def shortHelpString(self):
        return (
            "This tool aggregates multiple raster DEM tiles to a coarser resolution using "
            "block statistics, reproducing the behavior of the ArcGIS Aggregate tool.\n\n"

            "Parameters\n"
            "----------\n"
            "Rasters to aggregate : Raster (multiple)\n"
            "-> Input DEM tiles to be aggregated. The first raster defines the reference grid.\n\n"

            "Cell factor (integer) : Integer\n"
            "-> Aggregation factor applied to the original cell size (e.g. 10 converts 1 m cells "
            "to 10 m cells).\n\n"

            "Aggregation method : Choice\n"
            "-> Statistic used to aggregate input cells within each output cell (average, median, "
            "mode, minimum, or maximum).\n\n"

            "Expand extent if needed : Boolean\n"
            "-> If checked, the output extent is expanded so that full aggregation blocks fit. "
            "If unchecked, the extent is truncated so that only complete blocks are used.\n\n"

            "Ignore NoData in calculations : Boolean\n"
            "-> If checked, NoData values are ignored during aggregation. If unchecked, any NoData "
            "within a block will propagate to the output cell.\n\n"

            "Output location : Folder\n"
            "-> Directory where the aggregated rasters will be written.\n\n"

            "Returns\n"
            "-------\n"
            "Output folder\n"
            "-> A set of aggregated raster DEMs aligned on a common 10 m grid, ready for use in "
            "LISFLOOD and subsequent flood-modelling steps."
        )

# Helper functions
def snapped_extent(ext: QgsRectangle, cellsize: float, expand: bool) -> QgsRectangle:
    # Snap an extent to the target grid, optionally expanding to fit full cells
    xmin, ymin = ext.xMinimum(), ext.yMinimum()
    xmax, ymax = ext.xMaximum(), ext.yMaximum()

    width = xmax - xmin
    height = ymax - ymin
    if cellsize <= 0 or width <= 0 or height <= 0:
        return ext

    if expand:
        ncols = math.ceil(width / cellsize)
        nrows = math.ceil(height / cellsize)
    else:
        ncols = max(math.floor(width / cellsize), 1)
        nrows = max(math.floor(height / cellsize), 1)

    return QgsRectangle(xmin, ymin, xmin + ncols * cellsize, ymin + nrows * cellsize)

def snapped_extent_to_snap(ext: QgsRectangle, snap: QgsRasterLayer, cellsize: float, expand: bool) -> QgsRectangle:
    # Snap extent to the grid defined by the snap raster
    xmin, ymin = ext.xMinimum(), ext.yMinimum()
    xmax, ymax = ext.xMaximum(), ext.yMaximum()

    x0 = snap.extent().xMinimum()
    y0 = snap.extent().yMinimum()

    def snap_min(v, v0):
        t = (v - v0) / cellsize
        return v0 + (math.floor(t) if expand else math.ceil(t)) * cellsize

    def snap_max(v, v0):
        t = (v - v0) / cellsize
        return v0 + (math.ceil(t) if expand else math.floor(t)) * cellsize

    sxmin = snap_min(xmin, x0)
    symin = snap_min(ymin, y0)
    sxmax = snap_max(xmax, x0)
    symax = snap_max(ymax, y0)

    # Safety guard
    if sxmax <= sxmin:
        sxmax = sxmin + cellsize
    if symax <= symin:
        symax = symin + cellsize

    return QgsRectangle(sxmin, symin, sxmax, symax)