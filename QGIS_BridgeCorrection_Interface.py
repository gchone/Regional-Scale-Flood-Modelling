from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))

from BridgeCorrection import execute_BridgeCorrection
import QGIStools
from QGIS_Messages import Messages

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessing,
)


class QGIS_BridgeCorrection(QgsProcessingAlgorithm):
    DEM = "DEM"
    BRIDGES = "BRIDGES"
    OUTPUT = "OUTPUT"

    def name(self):
        return "bridgecorrection"

    def displayName(self):
        return "Bridges and culverts correction"

    def group(self):
        return "Large Scale Flood Modelling Toolbox"

    def groupId(self):
        return "large_scale_flood_modelling_toolbox"

    def createInstance(self):
        return QGIS_BridgeCorrection()

    def shortHelpString(self):
        return (
            "Bridges and culverts correction\n\n"
            "Rasterizes bridge polygons and their boundaries on the DEM grid, "
            "replaces each bridge zone with its minimum DEM elevation, applies a "
            "hydrological fill, and pastes the filled values back only on bridge cells."
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessingParameterRasterLayer,
            QgsProcessingParameterFeatureSource,
            QgsProcessingParameterRasterDestination,
        )

        self.addParameter(QgsProcessingParameterRasterLayer(self.DEM, "DEM (lidar3m_min)"))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.BRIDGES,
            "Bridges to be corrected (geometry.gpkg/bridges)",
            [QgsProcessing.TypeVectorPolygon],
        ))
        self.addParameter(QgsProcessingParameterRasterDestination(
            self.OUTPUT,
            "Result - Corrected DEM (lidar3m_forws)",
        ))

    def processAlgorithm(self, parameters, context, feedback):
        dem_layer = self.parameterAsRasterLayer(parameters, self.DEM, context)
        bridges_source = self.parameterAsSource(parameters, self.BRIDGES, context)
        output_path = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)

        if dem_layer is None:
            raise QgsProcessingException("Input DEM layer is invalid")
        if bridges_source is None:
            raise QgsProcessingException("Input bridges layer is invalid")

        result = execute_BridgeCorrection(
            dem_layer,
            bridges_source,
            output_path,
            GIStools=QGIStools,
            messages=Messages(feedback),
            language="EN",
        )
        return {self.OUTPUT: result}


BridgeCorrection = QGIS_BridgeCorrection
