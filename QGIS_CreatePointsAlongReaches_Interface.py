from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))

from CreatePointsAlongReaches import execute_CreatePointsAlongReaches
import QGIStools
from QGIS_Messages import Messages

from qgis.core import QgsProcessingAlgorithm, QgsProcessingException, QgsProcessing


class QGIS_CreatePointsAlongReaches(QgsProcessingAlgorithm):
    NETWORK_SHP = 'NETWORK_SHP'
    LINKS_TABLE = 'LINKS_TABLE'
    RID_FIELD = 'RID_FIELD'
    INTERVAL = 'INTERVAL'
    OUTPUT_PT = 'OUTPUT_PT'

    def name(self):
        return 'create_points_along_reaches'

    def displayName(self):
        return 'Create points along route feature class'

    def group(self):
        return 'Large Scale Flood Modelling Toolbox'

    def groupId(self):
        return 'large_scale_flood_modelling_toolbox'

    def createInstance(self):
        return QGIS_CreatePointsAlongReaches()

    def initAlgorithm(self, config=None):
        from qgis.core import QgsProcessingParameterVectorLayer, QgsProcessingParameterFeatureSource, QgsProcessingParameterField, QgsProcessingParameterDistance, QgsProcessingParameterFeatureSink
        self.addParameter(QgsProcessingParameterVectorLayer(self.NETWORK_SHP, 'Route feature class', [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.LINKS_TABLE, 'Route links table', [QgsProcessing.TypeVector]))
        self.addParameter(QgsProcessingParameterField(self.RID_FIELD, 'RouteID field in network feature class', parentLayerParameterName=self.NETWORK_SHP))
        self.addParameter(QgsProcessingParameterDistance(self.INTERVAL, 'Interval between points, in meters', defaultValue=5.0, parentParameterName=self.NETWORK_SHP))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_PT, 'Output: Point table'))

    def processAlgorithm(self, parameters, context, feedback):
        network_shp = self.parameterAsVectorLayer(parameters, self.NETWORK_SHP, context)
        links_table = self.parameterAsSource(parameters, self.LINKS_TABLE, context)
        rid_field = self.parameterAsString(parameters, self.RID_FIELD, context)
        interval = self.parameterAsDouble(parameters, self.INTERVAL, context)
        output_pt = self.parameterAsOutputLayer(parameters, self.OUTPUT_PT, context)
        if network_shp is None or links_table is None:
            raise QgsProcessingException('Input layer is invalid')
        execute_CreatePointsAlongReaches(network_shp, links_table, rid_field, interval, output_pt, GIStools=QGIStools, messages=Messages(feedback))
        return {self.OUTPUT_PT: output_pt}
