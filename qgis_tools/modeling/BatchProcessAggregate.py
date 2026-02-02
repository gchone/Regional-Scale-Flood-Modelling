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
        feedback.pushInfo(
            "Running GRASS r.resamp.stats in batch mode.\n"
            "Some GRASS warnings may appear in the log on Windows but do not affect results."
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
        cellsize_og = ref.rasterUnitsPerPixelX()

        # Compute snapped region extent using union of all rasters if expand=True
        if expand:
            union = union_extent(rasters)
            region = snapped_extent(union, cellsize_og, True)

        # Batch processing loop
        total = len(rasters)

        for i, lyr in enumerate(rasters):
            if feedback.isCanceled():
                break

            # Input raster path
            src = lyr.source()

            # Output file name (same base name + suffix)
            base = os.path.splitext(os.path.basename(src))[0]
            out_path = os.path.join(out_dir, f"{base}_agg.tif")

            feedback.pushInfo(f"Aggregating raster {i+1}/{total}: {base}")

            # Use current raster as-is unless expand=True
            src_for_grass = src

            if expand:
                # Warp tile to a common grid so all rasters share identical pixel alignment
                tmp_aligned = os.path.join(tempfile.gettempdir(), f"{base}_aligned_{os.getpid()}_{i + 1}.tif")

                alg_params = {
                    "INPUT": src,
                    "TARGET_EXTENT": f"{region.xMinimum()},{region.xMaximum()},{region.yMinimum()},{region.yMaximum()}",
                    "TARGET_EXTENT_CRS": ref.crs(),
                    "TARGET_RESOLUTION": cellsize_og,
                    "TARGET_ALIGNED_PIXELS": True,
                    "RESAMPLING": 0,  # nearest
                    "OUTPUT": tmp_aligned
                }
                processing.run(
                    "gdal:warpreproject",
                    alg_params,
                    context=context,
                    feedback=None,
                    is_child_algorithm=True
                )

                src_for_grass = tmp_aligned

            # Aggregate rasters using GRASS r.resamp.stats
            alg_params = {
                "input": src_for_grass,
                "method": tech_idx,
                "output": out_path,
                "-n": propagate_nulls,
                "GRASS_REGION_CELLSIZE_PARAMETER": cellsize,
                "GRASS_RASTER_FORMAT_OPT": "",
                "GRASS_RASTER_FORMAT_META": ""
            }
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
def union_extent(rasters):
    # Compute the bounding union extent of all input rasters
    xmin = ymin = xmax = ymax = None
    for r in rasters:
        e = r.extent()
        if xmin is None:
            xmin, ymin, xmax, ymax = e.xMinimum(), e.yMinimum(), e.xMaximum(), e.yMaximum()
        else:
            xmin = min(xmin, e.xMinimum())
            ymin = min(ymin, e.yMinimum())
            xmax = max(xmax, e.xMaximum())
            ymax = max(ymax, e.yMaximum())
    return QgsRectangle(xmin, ymin, xmax, ymax)


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

    snapped_xmax = xmin + ncols * cellsize
    snapped_ymax = ymin + nrows * cellsize

    return QgsRectangle(xmin, ymin, snapped_xmax, snapped_ymax)
