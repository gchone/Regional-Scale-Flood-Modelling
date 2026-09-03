from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))

from CreateNetworkFromFC import execute_CreateNetworkFromFC
import QGIStools
from QGIS_Messages import Messages

from qgis.core import QgsProcessingAlgorithm, QgsProcessingException, QgsProcessing


class QGIS_CreateNetworkFromFC(QgsProcessingAlgorithm):
    RIVERNET = 'RIVERNET'
    ROUTE_SHAPEFILE = 'ROUTE_SHAPEFILE'
    ROUTELINKS_TABLE = 'ROUTELINKS_TABLE'
    ROUTEID_FIELD = 'ROUTEID_FIELD'
    DOWNSTREAM_REACH_FIELD = 'DOWNSTREAM_REACH_FIELD'
    CHANNELTYPE_FIELD = 'CHANNELTYPE_FIELD'

    def name(self):
        return 'create_network_from_fc'

    def displayName(self):
        return 'Create network from feature class'

    def group(self):
        return 'Large Scale Flood Modelling Toolbox - Detailed Tools'

    def groupId(self):
        return 'large_scale_flood_modelling_toolbox_detailed_tools'

    def createInstance(self):
        return QGIS_CreateNetworkFromFC()

    def initAlgorithm(self, config=None):
        from qgis.core import QgsProcessingParameterVectorLayer, QgsProcessingParameterField, QgsProcessingParameterFeatureSink
        self.addParameter(QgsProcessingParameterVectorLayer(self.RIVERNET, 'Input feature class (lines)', [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterField(self.ROUTEID_FIELD, 'RouteID field', parentLayerParameterName=self.RIVERNET))
        self.addParameter(QgsProcessingParameterField(self.DOWNSTREAM_REACH_FIELD, 'Field identifying the most downstream reach', parentLayerParameterName=self.RIVERNET))
        self.addParameter(QgsProcessingParameterField(self.CHANNELTYPE_FIELD, 'Field identifying the main or secondary channel', parentLayerParameterName=self.RIVERNET, optional=True))
        self.addParameter(QgsProcessingParameterFeatureSink(self.ROUTE_SHAPEFILE, 'Output: Network layer'))
        self.addParameter(QgsProcessingParameterFeatureSink(self.ROUTELINKS_TABLE, 'Output: Link table'))

    def processAlgorithm(self, parameters, context, feedback):
        rivernet = self.parameterAsVectorLayer(parameters, self.RIVERNET, context)
        route_shapefile = self.parameterAsOutputLayer(parameters, self.ROUTE_SHAPEFILE, context)
        routelinks_table = self.parameterAsOutputLayer(parameters, self.ROUTELINKS_TABLE, context)
        routeID_field = self.parameterAsString(parameters, self.ROUTEID_FIELD, context)
        downstream_reach_field = self.parameterAsString(parameters, self.DOWNSTREAM_REACH_FIELD, context)
        channeltype_field = self.parameterAsString(parameters, self.CHANNELTYPE_FIELD, context)
        if rivernet is None:
            raise QgsProcessingException('Input feature class is invalid')
        execute_CreateNetworkFromFC(rivernet, route_shapefile, routelinks_table, routeID_field, downstream_reach_field, channeltype_field, GIStools=QGIStools, messages=Messages(feedback))
        return {self.ROUTE_SHAPEFILE: route_shapefile, self.ROUTELINKS_TABLE: routelinks_table}
