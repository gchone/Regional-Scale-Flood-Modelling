from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))

from CreateFromPointsAndSplits import execute_CreateFromPointsAndSplits
import QGIStools
from QGIS_Messages import Messages

from qgis.core import QgsProcessingAlgorithm, QgsProcessingException, QgsProcessing


class QGIS_CreateFromPointsAndSplits(QgsProcessingAlgorithm):
    NETWORK_SHP = 'NETWORK_SHP'
    LINKS_TABLE = 'LINKS_TABLE'
    RID_FIELD = 'RID_FIELD'
    POINTS = 'POINTS'
    SPLITS = 'SPLITS'

    def name(self):
        return 'create_from_points_and_splits'

    def displayName(self):
        return 'Create from points and split points'

    def group(self):
        return 'Large Scale Flood Modelling Toolbox'

    def groupId(self):
        return 'large_scale_flood_modelling_toolbox'

    def createInstance(self):
        return QGIS_CreateFromPointsAndSplits()

    def initAlgorithm(self, config=None):
        from qgis.core import QgsProcessingParameterVectorLayer, QgsProcessingParameterFeatureSource, QgsProcessingParameterField, QgsProcessingParameterFeatureSink
        self.addParameter(QgsProcessingParameterVectorLayer(self.NETWORK_SHP, 'Network feature class', [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.LINKS_TABLE, 'Link table', [QgsProcessing.TypeVector]))
        self.addParameter(QgsProcessingParameterField(self.RID_FIELD, 'RouteID field in the network feature class', parentLayerParameterName=self.NETWORK_SHP))
        self.addParameter(QgsProcessingParameterFeatureSink(self.POINTS, 'Output: From points feature class'))
        self.addParameter(QgsProcessingParameterFeatureSink(self.SPLITS, 'Output: Split points feature class'))

    def processAlgorithm(self, parameters, context, feedback):
        network_shp = self.parameterAsVectorLayer(parameters, self.NETWORK_SHP, context)
        links_table = self.parameterAsSource(parameters, self.LINKS_TABLE, context)
        rid_field = self.parameterAsString(parameters, self.RID_FIELD, context)
        points = self.parameterAsOutputLayer(parameters, self.POINTS, context)
        splits = self.parameterAsOutputLayer(parameters, self.SPLITS, context)
        if network_shp is None:
            raise QgsProcessingException('Network feature class is invalid')
        if links_table is None:
            raise QgsProcessingException('Link table is invalid')
        execute_CreateFromPointsAndSplits(network_shp, links_table, rid_field, points, splits, GIStools=QGIStools, messages=Messages(feedback))
        return {self.POINTS: points, self.SPLITS: splits}
