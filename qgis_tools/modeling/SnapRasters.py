import os
import subprocess

from osgeo import gdal
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterCrs,
    QgsProcessingParameterFolderDestination,
)


# =============================================================================
# QgsProcessingAlgorithm
# =============================================================================

class SnapRasters(QgsProcessingAlgorithm):

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
            "Snaps a set of rasters to the grid of a reference raster using gdalwarp, "
            "ensuring that all cell edges align exactly with the reference grid. "
            "This is equivalent to ArcGIS's Snap Raster environment setting.\n\n"
            "Inputs:\n"
            "- Rasters to snap: input rasters to be aligned\n"
            "- Reference raster: the raster whose grid origin, resolution, and extent "
            "all inputs will be snapped to\n"
            "- Output CRS (optional): if the input rasters have no CRS defined, "
            "specify it here so it is written to all output files\n"
            "- Output location: directory where snapped rasters will be written\n\n"
            "Output:\n"
            "- Snapped rasters with cell edges aligned to the reference raster's grid\n"
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterMultipleLayers(
            self.INPUT_RASTERS, "Rasters to snap",
            layerType=QgsProcessing.TypeRaster,
        ))
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.REFERENCE_RASTER, "Reference raster",
        ))
        self.addParameter(QgsProcessingParameterCrs(
            self.CRS,
            "Output CRS (optional — assign if input rasters have no CRS defined)",
            optional=True,
        ))
        self.addParameter(QgsProcessingParameterFolderDestination(
            self.OUT_DIR, "Output location",
        ))

    def processAlgorithm(self, parameters, context, feedback):
        rasters   = self.parameterAsLayerList(parameters, self.INPUT_RASTERS, context)
        ref_layer = self.parameterAsRasterLayer(parameters, self.REFERENCE_RASTER, context)
        out_dir   = self.parameterAsString(parameters, self.OUT_DIR, context)
        crs       = self.parameterAsCrs(parameters, self.CRS, context)

        if not rasters:
            raise QgsProcessingException("No rasters provided.")

        execute_snap_rasters(rasters, ref_layer, out_dir, crs, feedback)

        return {"OUTPUT_FOLDER": out_dir}


# =============================================================================
# Core logic
# =============================================================================

def execute_snap_rasters(rasters, ref_layer, out_dir, crs, feedback):

    # ------------------------------------------------------------------
    # Read reference raster grid
    # ------------------------------------------------------------------
    ref_ds = gdal.Open(ref_layer.source(), gdal.GA_ReadOnly)
    if ref_ds is None:
        raise QgsProcessingException(
            f"Could not open reference raster: {ref_layer.source()}"
        )

    ref_gt   = ref_ds.GetGeoTransform()
    ref_cols = ref_ds.RasterXSize
    ref_rows = ref_ds.RasterYSize
    ref_ds   = None

    ref_xmin  = ref_gt[0]
    ref_ymax  = ref_gt[3]
    ref_res_x = ref_gt[1]
    ref_res_y = abs(ref_gt[5])
    ref_xmax  = ref_xmin + ref_cols * ref_res_x
    ref_ymin  = ref_ymax - ref_rows * ref_res_y

    feedback.pushInfo(
        f"Reference grid — origin: ({ref_xmin}, {ref_ymax}), "
        f"extent: ({ref_xmin}, {ref_ymin}, {ref_xmax}, {ref_ymax}), "
        f"resolution: ({ref_res_x}, {ref_res_y}), "
        f"size: {ref_cols}x{ref_rows}"
    )

    # ------------------------------------------------------------------
    # Snap each raster to reference grid using gdalwarp -te
    # ------------------------------------------------------------------
    total = len(rasters)

    for i, lyr in enumerate(rasters):
        if feedback.isCanceled():
            break

        src      = lyr.source()
        base     = os.path.splitext(os.path.basename(src))[0]
        out_path = os.path.join(out_dir, f"{base}_snapped.tif")

        feedback.pushInfo(f"Snapping raster {i + 1}/{total}: {base}")

        ds = gdal.Open(src, gdal.GA_ReadOnly)
        if ds is None:
            feedback.pushWarning(f"Could not open {src} — skipping.")
            continue

        nodata     = ds.GetRasterBand(1).GetNoDataValue()
        projection = ds.GetProjection()
        ds         = None

        cmd = [
            'gdalwarp',
            '-overwrite',
            '-of', 'GTiff',
            '-te', str(ref_xmin), str(ref_ymin), str(ref_xmax), str(ref_ymax),
            '-tr', str(ref_res_x), str(ref_res_y),
            '-r', 'bilinear',
            '-co', 'COMPRESS=LZW',
            '-co', 'TILED=YES',
        ]

        if nodata is not None:
            cmd += ['-dstnodata', str(nodata)]

        if crs and crs.isValid():
            cmd += ['-t_srs', crs.authid()]
        elif projection:
            cmd += ['-t_srs', projection]

        cmd += [src, out_path]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            feedback.pushWarning(f"gdalwarp error for {base}:\n{result.stderr}")
        else:
            feedback.pushInfo(f"Finished {i + 1}/{total}: {base} → {out_path}")

        feedback.setProgress(int((i + 1) * 100 / total))