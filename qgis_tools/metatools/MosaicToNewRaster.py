import os
import subprocess
from osgeo import gdal
from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessing,
)
import processing


class MosaicToNewRaster(QgsProcessingAlgorithm):

    INPUT_RASTERS = "INPUT_RASTERS"
    RESAMPLING = "RESAMPLING"
    NODATA = "NODATA"
    OUTPUT = "OUTPUT"

    RESAMPLING_OPTIONS = [
        "Nearest neighbour",
        "Average",
        "Minimum",
        "Maximum",
        "Median",
    ]
    RESAMPLING_GDAL = [
        "near",
        "average",
        "min",
        "max",
        "med",
    ]

    def name(self):
        return "mosaictonewraster"

    def displayName(self):
        return "Mosaic to new raster"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Metatools"

    def groupId(self):
        return "concordiariverlab_floodtools_metatools"

    def createInstance(self):
        return MosaicToNewRaster()

    def shortHelpString(self):
        return (
            "Mosaic to New Raster\n\n"
            "Merges multiple raster tiles into a single raster using a VRT intermediate. "
            "Equivalent to ArcGIS Mosaic to New Raster.\n\n"
            "Inputs:\n"
            "- Input rasters: raster tiles to mosaic\n"
            "- Resampling method: statistic used in overlap zones\n"
            "  - Nearest neighbour: use for categorical data (e.g. flow direction)\n"
            "  - Minimum: use for water surface DEMs\n"
            "  - Average/Maximum/Median: other use cases\n"
            "- NoData value: NoData value for input and output (default: -9999)\n\n"
            "Output:\n"
            "- Mosaicked raster\n"
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessingParameterMultipleLayers,
            QgsProcessingParameterEnum,
            QgsProcessingParameterNumber,
            QgsProcessingParameterRasterDestination,
        )

        self.addParameter(QgsProcessingParameterMultipleLayers(
            self.INPUT_RASTERS,
            "Input rasters",
            layerType=QgsProcessing.TypeRaster,
        ))
        self.addParameter(QgsProcessingParameterEnum(
            self.RESAMPLING,
            "Resampling method",
            options=self.RESAMPLING_OPTIONS,
            defaultValue=0,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.NODATA,
            "NoData value",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=-9999.0,
        ))
        self.addParameter(QgsProcessingParameterRasterDestination(
            self.OUTPUT,
            "Output raster",
        ))

    def processAlgorithm(self, parameters, context, feedback):
        from qgis.core import QgsProcessingParameterNumber

        rasters = self.parameterAsLayerList(parameters, self.INPUT_RASTERS, context)
        resampling_idx = self.parameterAsEnum(parameters, self.RESAMPLING, context)
        nodata_val = self.parameterAsDouble(parameters, self.NODATA, context)
        output_path = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)

        if not rasters:
            raise QgsProcessingException("No input rasters provided")

        result = execute_mosaic_to_new_raster(
            rasters, resampling_idx, nodata_val, output_path, feedback
        )
        return {self.OUTPUT: result}


# =============================================================================
# Helpers
# =============================================================================

def _vrt_resampling_index(gdal_method):
    """
    Maps GDAL resampling method string to gdal:buildvirtualraster RESAMPLING index.
    0=nearest, 1=bilinear, 2=cubic, 3=cubicspline, 4=lanczos, 5=average, 6=mode,
    7=min, 8=max, 9=med
    """
    mapping = {
        "near":    0,
        "average": 5,
        "min":     7,
        "max":     8,
        "med":     9,
    }
    return mapping.get(gdal_method, 0)

# =============================================================================
# Core logic
# =============================================================================

def execute_mosaic_to_new_raster(rasters, resampling_idx, nodata_val, output_path, feedback):
    """
    Mosaics multiple raster layers into a single output raster via VRT.

    Parameters
    ----------
    rasters         : list of QgsRasterLayer
    resampling_idx  : int - index into RESAMPLING_GDAL
    nodata_val      : float
    output_path     : str
    feedback        : QgsProcessingFeedback

    Returns
    -------
    output_path : str
    """
    resampling_gdal = ["near", "average", "min", "max", "med"]
    resampling = resampling_gdal[resampling_idx]

    input_paths = [r.source() for r in rasters]
    feedback.pushInfo(f"Mosaicking {len(input_paths)} rasters with resampling={resampling}...")

    tmp_vrt = output_path.replace(".tif", ".vrt")
    if not tmp_vrt.endswith(".vrt"):
        tmp_vrt = output_path + ".vrt"

    # Step 1: Build VRT
    feedback.pushInfo("Building VRT...")
    processing.run("gdal:buildvirtualraster", {
        'INPUT':            input_paths,
        'RESOLUTION':       0,
        'SEPARATE':         False,
        'PROJ_DIFFERENCE':  False,
        'ADD_ALPHA':        False,
        'ASSIGN_CRS':       None,
        'RESAMPLING':       _vrt_resampling_index(resampling),
        'SRC_NODATA':       str(nodata_val),
        'OUTPUT':           tmp_vrt,
    })

    # Step 2: Translate VRT to TIF
    feedback.pushInfo("Converting VRT to raster...")
    processing.run("gdal:translate", {
        'INPUT':     tmp_vrt,
        'NODATA':    nodata_val,
        'DATA_TYPE': 0,  # use input data type
        'OUTPUT':    output_path,
    })

    # Cleanup VRT
    if os.path.exists(tmp_vrt):
        os.remove(tmp_vrt)

    feedback.pushInfo(f"Done — saved to {output_path}")
    return output_path


