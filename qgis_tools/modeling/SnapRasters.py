import os
import math
import subprocess

from osgeo import (
    gdal,
    osr,
)
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterCrs,
    QgsProcessingParameterFolderDestination,
)


class SnapRasters(QgsProcessingAlgorithm):
    """
    Snaps a set of raster DEMs to the grid of a reference raster using gdal_translate.

    All input rasters are resampled so that their cell edges align exactly with
    the reference raster's grid (origin + resolution). This is equivalent to
    ArcGIS's Snap Raster environment setting.
    """

    INPUT_RASTERS    = "INPUT_RASTERS"
    REFERENCE_RASTER = "REFERENCE_RASTER"
    CRS              = "CRS"
    OUT_DIR          = "OUT_DIR"

    def name(self):
        return "snap_rasters"

    def displayName(self):
        return "Snap rasters"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Modeling"

    def groupId(self):
        return "concordiariverlab_floodtools_modeling"

    def createInstance(self):
        return SnapRasters()

    def shortHelpString(self):
        return (
            "Snap Rasters\n\n"
            "Snaps a set of raster DEMs to the grid of a reference raster, "
            "ensuring that all cell edges align exactly. This is equivalent to "
            "ArcGIS's Snap Raster environment setting.\n\n"
            "Inputs:\n"
            "- Rasters to snap: input DEM tiles to be aligned.\n"
            "- Reference raster: the raster whose grid origin and resolution "
            "all inputs will be snapped to.\n"
            "- Output CRS (optional): if the input rasters have no CRS defined, "
            "specify it here so it is written to all output files.\n"
            "- Output location: directory where snapped rasters will be written.\n\n"
            "Output:\n"
            "- A set of snapped raster DEMs with cell edges aligned to the "
            "reference raster's grid, ready for mosaicking or further analysis.\n"
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                self.INPUT_RASTERS,
                "Rasters to snap",
                layerType=QgsProcessing.TypeRaster,
            )
        )

        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.REFERENCE_RASTER,
                "Reference raster",
            )
        )

        self.addParameter(
            QgsProcessingParameterCrs(
                self.CRS,
                "Output CRS (optional — assign if input rasters have no CRS defined)",
                optional=True,
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
        rasters   = self.parameterAsLayerList(parameters, self.INPUT_RASTERS, context)
        ref_layer = self.parameterAsRasterLayer(parameters, self.REFERENCE_RASTER, context)
        out_dir   = self.parameterAsString(parameters, self.OUT_DIR, context)
        crs       = self.parameterAsCrs(parameters, self.CRS, context)

        if not rasters:
            raise QgsProcessingException("No rasters provided.")

        # --- Read reference raster grid ---
        ref_ds = gdal.Open(ref_layer.source(), gdal.GA_ReadOnly)
        if ref_ds is None:
            raise QgsProcessingException(
                f"Could not open reference raster: {ref_layer.source()}"
            )

        ref_gt  = ref_ds.GetGeoTransform()
        ref_ds  = None

        ref_origin_x = ref_gt[0]   # top-left X
        ref_origin_y = ref_gt[3]   # top-left Y
        ref_res_x    = ref_gt[1]   # pixel width  (positive)
        ref_res_y    = abs(ref_gt[5])  # pixel height (stored negative, use abs)

        feedback.pushInfo(
            f"Reference grid — origin: ({ref_origin_x}, {ref_origin_y}), "
            f"resolution: ({ref_res_x}, {ref_res_y})"
        )

        total = len(rasters)

        for i, lyr in enumerate(rasters):
            if feedback.isCanceled():
                break

            src  = lyr.source()
            base = os.path.splitext(os.path.basename(src))[0]
            out_path = os.path.join(out_dir, f"{base}_snapped.tif")

            feedback.pushInfo(f"Snapping raster {i + 1}/{total}: {base}")

            ds = gdal.Open(src, gdal.GA_ReadOnly)
            if ds is None:
                feedback.pushWarning(f"Could not open {src} — skipping.")
                continue

            gt         = ds.GetGeoTransform()
            nodata     = ds.GetRasterBand(1).GetNoDataValue()
            projection = ds.GetProjection()
            cols       = ds.RasterXSize
            rows       = ds.RasterYSize
            ds         = None

            xmin = gt[0]
            ymax = gt[3]
            xmax = xmin + cols * ref_res_x
            ymin = ymax - rows * ref_res_y

            # Snap extent to reference grid
            # Floor/ceil in units of the reference grid offset from its origin
            snapped_xmin = ref_origin_x + math.floor(
                (xmin - ref_origin_x) / ref_res_x) * ref_res_x
            snapped_ymin = ref_origin_y - math.ceil(
                (ref_origin_y - ymin) / ref_res_y) * ref_res_y
            snapped_xmax = ref_origin_x + math.ceil(
                (xmax - ref_origin_x) / ref_res_x) * ref_res_x
            snapped_ymax = ref_origin_y - math.floor(
                (ref_origin_y - ymax) / ref_res_y) * ref_res_y

            ncols = round((snapped_xmax - snapped_xmin) / ref_res_x)
            nrows = round((snapped_ymax - snapped_ymin) / ref_res_y)

            cmd = [
                "gdal_translate",
                "-projwin",
                    str(snapped_xmin), str(snapped_ymax),
                    str(snapped_xmax), str(snapped_ymin),
                "-outsize", str(ncols), str(nrows),
                "-r", "bilinear",
                "-co", "COMPRESS=LZW",
                "-co", "TILED=YES",
            ]

            if nodata is not None:
                cmd += ["-a_nodata", str(nodata)]

            # Use user-supplied CRS if provided, otherwise carry through input CRS
            if crs and crs.isValid():
                cmd += ["-a_srs", crs.authid()]
            elif projection:
                cmd += ["-a_srs", projection]

            cmd += [src, out_path]

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                feedback.pushWarning(f"gdal_translate error for {base}:\n{result.stderr}")
            else:
                feedback.pushInfo(f"Finished {i + 1}/{total}: {base} → {out_path}")

            feedback.setProgress(int((i + 1) * 100 / total))

        return {"OUTPUT_FOLDER": out_dir}