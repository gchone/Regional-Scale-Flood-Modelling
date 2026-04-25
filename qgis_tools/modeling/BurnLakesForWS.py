import os
import numpy as np
from osgeo import gdal
from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessing,
)
import processing


class BurnLakesForWS(QgsProcessingAlgorithm):

    DEM = "DEM"
    ROUTES_MAIN = "ROUTES_MAIN"
    LAKES = "LAKES"
    OUTPUT = "OUTPUT"

    BURN_DEPTH = 10  # metres, hardcoded to match ArcGIS original

    def name(self):
        return "burnlakesforws"

    def displayName(self):
        return "Burn lakes for water surface assessment"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Modeling"

    def groupId(self):
        return "concordiariverlab_floodtools_modeling"

    def createInstance(self):
        return BurnLakesForWS()

    def shortHelpString(self):
        return (
            "Burn Lakes for Water Surface Assessment\n\n"
            "Burns the river centreline through lakes into the DEM by lowering elevation "
            "along the river path through lake polygons by 10m. This forces flow direction "
            "to route correctly through lake areas.\n\n"
            "Inputs:\n"
            "- DEM for water surface assessment: lidar3m_forws\n"
            "- Routes main: main river network line layer (routes_main)\n"
            "- Lakes: lake polygon layer (lakesfinal)\n\n"
            "Output:\n"
            "- Burned DEM (lidar3m_forws_lakes): DEM with river path through lakes "
            "lowered by 10m. Use this in all subsequent steps instead of lidar3m_forws.\n"
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessingParameterRasterLayer,
            QgsProcessingParameterVectorLayer,
            QgsProcessingParameterRasterDestination,
        )

        self.addParameter(QgsProcessingParameterRasterLayer(
            self.DEM, "DEM for water surface assessment"
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.ROUTES_MAIN, "Routes main",
            [QgsProcessing.TypeVectorLine]
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.LAKES, "Lakes (lakesfinal)",
            [QgsProcessing.TypeVectorPolygon]
        ))
        self.addParameter(QgsProcessingParameterRasterDestination(
            self.OUTPUT, "Result - Burned DEM"
        ))

    def processAlgorithm(self, parameters, context, feedback):
        dem_layer = self.parameterAsRasterLayer(parameters, self.DEM, context)
        routes_main = self.parameterAsVectorLayer(parameters, self.ROUTES_MAIN, context)
        lakes = self.parameterAsVectorLayer(parameters, self.LAKES, context)
        output_path = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)

        if dem_layer is None:
            raise QgsProcessingException("Input DEM layer is invalid")
        if routes_main is None:
            raise QgsProcessingException("Input routes main layer is invalid")
        if lakes is None:
            raise QgsProcessingException("Input lakes layer is invalid")

        result = execute_burn_lakes_for_ws(
            dem_layer, routes_main, lakes, output_path, self.BURN_DEPTH, feedback
        )
        return {self.OUTPUT: result}


# =============================================================================
# Core logic
# =============================================================================

def execute_burn_lakes_for_ws(dem_layer, routes_main, lakes, output_path, burn_depth, feedback):
    """
    Burns the river centreline through lakes into the DEM.

    Parameters
    ----------
    dem_layer   : QgsRasterLayer
    routes_main : QgsVectorLayer - main river network lines
    lakes       : QgsVectorLayer - lake polygons (lakesfinal)
    output_path : str
    burn_depth  : float - metres to lower DEM along river path through lakes
    feedback    : QgsProcessingFeedback

    Returns
    -------
    output_path : str
    """
    dem_path = dem_layer.source()
    tmp_dir = os.path.dirname(output_path)
    tmp_clip = os.path.join(tmp_dir, "_tmp_routes_lakes.gpkg")
    tmp_rv = os.path.join(tmp_dir, "_tmp_routes_lakes_rv.gpkg")
    tmp_burn = os.path.join(tmp_dir, "_tmp_lakes_burn.tif")

    try:
        # Step 1: Clip routes_main to lakes
        feedback.pushInfo("Clipping routes_main to lakes...")
        result = processing.run("native:clip", {
            'INPUT': routes_main,
            'OVERLAY': lakes,
            'OUTPUT': tmp_clip
        })
        routes_clipped = result['OUTPUT']

        # Step 2: Add rastervalue field = 1
        feedback.pushInfo("Adding rastervalue field...")
        result = processing.run("native:fieldcalculator", {
            'INPUT': routes_clipped,
            'FIELD_NAME': 'rastervalue',
            'FIELD_TYPE': 1,
            'FORMULA': '1',
            'OUTPUT': tmp_rv
        })
        routes_rv = result['OUTPUT']

        # Step 3: Rasterize to match DEM extent and resolution
        feedback.pushInfo("Rasterizing river path through lakes...")
        ds = gdal.Open(dem_path)
        gt = ds.GetGeoTransform()
        xres = gt[1]
        yres = abs(gt[5])
        extent = (
            f"{gt[0]},{gt[0] + ds.RasterXSize * xres},"
            f"{gt[3] + ds.RasterYSize * -yres},{gt[3]}"
        )
        ds = None

        processing.run("gdal:rasterize", {
            'INPUT': routes_rv,
            'FIELD': 'rastervalue',
            'BURN': 0,
            'USE_Z': False,
            'UNITS': 1,
            'WIDTH': xres,
            'HEIGHT': yres,
            'EXTENT': extent,
            'NODATA': -9999,
            'DATA_TYPE': 5,
            'OUTPUT': tmp_burn
        })

        # Step 4: Burn into DEM using numpy
        feedback.pushInfo("Burning river path into DEM...")
        dem_ds = gdal.Open(dem_path)
        burn_ds = gdal.Open(tmp_burn)

        gt = dem_ds.GetGeoTransform()
        proj = dem_ds.GetProjection()
        cols = dem_ds.RasterXSize
        rows = dem_ds.RasterYSize

        dem_array = dem_ds.GetRasterBand(1).ReadAsArray().astype(np.float32)
        burn_array = burn_ds.GetRasterBand(1).ReadAsArray()
        dem_ds = None
        burn_ds = None

        result_array = np.where(burn_array == 1, dem_array - burn_depth, dem_array)

        out_ds = gdal.GetDriverByName("GTiff").Create(
            output_path, cols, rows, 1, gdal.GDT_Float32
        )
        out_ds.SetGeoTransform(gt)
        out_ds.SetProjection(proj)
        out_ds.GetRasterBand(1).SetNoDataValue(-9999.0)
        out_ds.GetRasterBand(1).WriteArray(result_array)
        out_ds.FlushCache()
        out_ds = None

        feedback.pushInfo("Burn lakes complete.")
        return output_path

    finally:
        for tmp in [tmp_clip, tmp_rv, tmp_burn]:
            if os.path.exists(tmp):
                os.remove(tmp)