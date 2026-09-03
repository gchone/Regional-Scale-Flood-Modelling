from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))
from D4FlowDirection import *
import QGIStools
from QGIS_Messages import Messages

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessing,
)


class QGIS_D4FlowDirection(QgsProcessingAlgorithm):
    FLOWDIR = "FLOWDIR"
    DEM = "DEM"
    FROMPOINT = "FROMPOINT"
    OUTPUT = "OUTPUT"

    def name(self):
        return "d4flowdirection"

    def displayName(self):
        return "D4 flow direction"

    def group(self):
        return "Large Scale Flood Modelling Toolbox - Detailed Tools"

    def groupId(self):
        return "large_scale_flood_modelling_toolbox_detailed_tools"

    def createInstance(self):
        return QGIS_D4FlowDirection()

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
        )

        self.addParameter(QgsProcessingParameterRasterLayer(self.FLOWDIR, "lidar10m_fd"))
        self.addParameter(QgsProcessingParameterRasterLayer(self.DEM, "lidar10m_fill"))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.FROMPOINT, "from_pts", [QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterRasterDestination(self.OUTPUT, "D4 flow direction (d4fd)"))

    def processAlgorithm(self, parameters, context, feedback):
        flowdir_layer = self.parameterAsRasterLayer(parameters, self.FLOWDIR, context)
        dem_layer = self.parameterAsRasterLayer(parameters, self.DEM, context)
        frompoint_source = self.parameterAsSource(parameters, self.FROMPOINT, context)
        output_path = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)

        if flowdir_layer is None:
            raise QgsProcessingException("Flow direction raster is invalid")
        if dem_layer is None:
            raise QgsProcessingException("DEM raster is invalid")
        if frompoint_source is None:
            raise QgsProcessingException("From points layer is invalid")

        result = execute_D4FlowDirection(
            flowdir_layer,
            dem_layer,
            frompoint_source,
            output_path,
            QGIStools,
            Messages(feedback),
        )
        return {self.OUTPUT: result}
