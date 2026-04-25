import os
import math
import subprocess

from osgeo import gdal
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterNumber,
    QgsProcessingParameterEnum,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFolderDestination,
)


class BatchProcessAggregate(QgsProcessingAlgorithm):
    """
    Batch aggregation of raster DEM tiles using gdal_translate.

    Reproduces the behavior of the ArcGIS Aggregate tool by:
    - aggregating rasters by an integer factor using true block statistics,
    - truncating extent to only full output cells (no phantom pixels),
    - aligning all outputs to a common grid snapped to multiples of the target resolution,
    - supporting multiple aggregation statistics.
    """

    INPUT_RASTERS = "INPUT_RASTERS"
    FACTOR        = "FACTOR"
    TECH          = "TECH"
    IGNORE_NODATA = "IGNORE_NODATA"
    OUT_DIR       = "OUT_DIR"

    TECH_OPTIONS = ["average", "median", "mode", "minimum", "maximum"]
    TECH_GDAL    = ["average", "med",    "mode", "min",     "max"    ]

    def name(self):
        return "batch_process_aggregate"

    def displayName(self):
        return "Batch process aggregate"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Modeling"

    def groupId(self):
        return "concordiariverlab_floodtools_modeling"

    def createInstance(self):
        return BatchProcessAggregate()

    def shortHelpString(self):
        return (
            "Batch Process Aggregate\n\n"
            "Aggregates multiple raster DEM tiles to a coarser resolution using "
            "true block statistics, reproducing the behavior of the ArcGIS Aggregate tool. "
            "Extent is truncated to only full output cells — no phantom pixels at edges.\n\n"
            "Inputs:\n"
            "- Rasters to aggregate: input DEM tiles.\n"
            "- Cell factor (integer): aggregation factor applied to the original cell size "
            "(e.g. 10 converts 1m cells to 10m cells).\n"
            "- Aggregation method: statistic used to aggregate input cells within each output cell "
            "(average, median, mode, minimum, or maximum).\n"
            "- Ignore NoData in calculations: if checked, NoData values are ignored during "
            "aggregation. If unchecked, any NoData within a block propagates to the output cell.\n"
            "- Output location: directory where aggregated rasters will be written.\n\n"
            "Output:\n"
            "- A set of aggregated raster DEMs ready for use in LISFLOOD and subsequent "
            "flood-modelling steps.\n"
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                self.INPUT_RASTERS,
                "Rasters to aggregate",
                layerType=QgsProcessing.TypeRaster,
            )
        )

        self.addParameter(
            QgsProcessingParameterNumber(
                self.FACTOR,
                "Cell factor (3, 10)",
                type=QgsProcessingParameterNumber.Integer,
                defaultValue=10,
                minValue=1,
            )
        )

        self.addParameter(
            QgsProcessingParameterEnum(
                self.TECH,
                "Aggregation method (average, minimum)",
                options=self.TECH_OPTIONS,
                defaultValue=0,
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.IGNORE_NODATA,
                "Ignore NoData in calculations",
                defaultValue=True,
            )
        )

        self.addParameter(
            QgsProcessingParameterFolderDestination(
                self.OUT_DIR,
                "Output location",
            )
        )

    # =============================================================================
    # Core logic
    # =============================================================================

    def processAlgorithm(self, parameters, context, feedback):
        rasters = self.parameterAsLayerList(parameters, self.INPUT_RASTERS, context)
        if not rasters:
            raise QgsProcessingException("No rasters provided")

        factor        = self.parameterAsInt(parameters, self.FACTOR, context)
        tech_idx      = self.parameterAsEnum(parameters, self.TECH, context)
        ignore_nodata = self.parameterAsBool(parameters, self.IGNORE_NODATA, context)
        out_dir       = self.parameterAsString(parameters, self.OUT_DIR, context)

        tech  = self.TECH_GDAL[tech_idx]
        total = len(rasters)

        for i, lyr in enumerate(rasters):
            if feedback.isCanceled():
                break

            src  = lyr.source()
            base = os.path.splitext(os.path.basename(src))[0]
            out_path = os.path.join(out_dir, f"{base}_agg.tif")

            feedback.pushInfo(f"Aggregating raster {i + 1}/{total}: {base}")

            ds = gdal.Open(src, gdal.GA_ReadOnly)
            if ds is None:
                feedback.pushWarning(f"Could not open {src} — skipping.")
                continue

            gt      = ds.GetGeoTransform()
            nodata  = ds.GetRasterBand(1).GetNoDataValue()
            src_res = gt[1]
            ds_cols = ds.RasterXSize
            ds_rows = ds.RasterYSize
            ds      = None

            target_res = src_res * factor

            # Manually snap extent to target resolution grid
            # (replaces -tap which requires GDAL 3.14+)
            xmin = gt[0]
            ymax = gt[3]
            xmax = xmin + ds_cols * src_res
            ymin = ymax - ds_rows * src_res

            snapped_xmin = math.floor(xmin / target_res) * target_res
            snapped_ymin = math.floor(ymin / target_res) * target_res
            snapped_xmax = math.ceil(xmax / target_res) * target_res
            snapped_ymax = math.ceil(ymax / target_res) * target_res

            ncols = round((snapped_xmax - snapped_xmin) / target_res)
            nrows = round((snapped_ymax - snapped_ymin) / target_res)

            cmd = [
                "gdal_translate",
                "-projwin", str(snapped_xmin), str(snapped_ymax),
                            str(snapped_xmax), str(snapped_ymin),
                "-outsize",  str(ncols), str(nrows),
                "-r", tech,
                "-co", "COMPRESS=LZW",
                "-co", "TILED=YES",
            ]

            if nodata is not None:
                cmd += ["-a_nodata", str(nodata)]

            if not ignore_nodata and nodata is not None:
                cmd += ["-srcnodata", str(nodata)]

            cmd += [src, out_path]

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                feedback.pushWarning(f"gdal_translate error for {base}:\n{result.stderr}")
            else:
                feedback.pushInfo(f"Finished {i + 1}/{total}: {base} → {out_path}")

            feedback.setProgress(int((i + 1) * 100 / total))

        return {"OUTPUT_FOLDER": out_dir}