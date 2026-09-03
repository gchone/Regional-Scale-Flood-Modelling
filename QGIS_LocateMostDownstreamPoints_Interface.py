from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))

from LocateMostDownstreamPoints import execute_LocateMostDownstreamPoints
import QGIStools
from QGIS_Messages import Messages

from qgis.core import QgsProcessingAlgorithm, QgsProcessingException, QgsProcessing


class QGIS_LocateMostDownstreamPoints(QgsProcessingAlgorithm):
    NETWORK_SHP = 'NETWORK_SHP'
    LINKS_TABLE = 'LINKS_TABLE'
    RID_FIELD = 'RID_FIELD'
    DATAPOINTS = 'DATAPOINTS'
    ID_FIELD_PTS = 'ID_FIELD_PTS'
    RID_FIELD_PTS = 'RID_FIELD_PTS'
    DISTANCE_FIELD_PTS = 'DISTANCE_FIELD_PTS'
    X_FIELD_PTS = 'X_FIELD_PTS'
    Y_FIELD_PTS = 'Y_FIELD_PTS'
    OUTPUT_PTS = 'OUTPUT_PTS'

    def name(self):
        return 'locate_most_downstream_points'

    def displayName(self):
        return 'Locate most downstream points on network'

    def group(self):
        return 'Large Scale Flood Modelling Toolbox - Detailed Tools'

    def groupId(self):
        return 'large_scale_flood_modelling_toolbox_detailed_tools'

    def createInstance(self):
        return QGIS_LocateMostDownstreamPoints()

    def initAlgorithm(self, config=None):
        from qgis.core import QgsProcessingParameterVectorLayer, QgsProcessingParameterFeatureSource, QgsProcessingParameterField, QgsProcessingParameterFeatureSink
        self.addParameter(QgsProcessingParameterVectorLayer(self.NETWORK_SHP, 'Network feature class', [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.LINKS_TABLE, 'Link table', [QgsProcessing.TypeVector]))
        self.addParameter(QgsProcessingParameterField(self.RID_FIELD, 'RouteID field in the network feature class', parentLayerParameterName=self.NETWORK_SHP))
        self.addParameter(QgsProcessingParameterFeatureSource(self.DATAPOINTS, 'Flow direction pixels along flow path table', [QgsProcessing.TypeVector]))
        self.addParameter(QgsProcessingParameterField(self.ID_FIELD_PTS, 'ID field name from flow-path points table', parentLayerParameterName=self.DATAPOINTS))
        self.addParameter(QgsProcessingParameterField(self.RID_FIELD_PTS, 'RouteID field name from flow-path points table', parentLayerParameterName=self.DATAPOINTS))
        self.addParameter(QgsProcessingParameterField(self.DISTANCE_FIELD_PTS, 'Distance field name from flow-path points table', parentLayerParameterName=self.DATAPOINTS))
        self.addParameter(QgsProcessingParameterField(self.X_FIELD_PTS, 'X field name from flow-path points table', parentLayerParameterName=self.DATAPOINTS))
        self.addParameter(QgsProcessingParameterField(self.Y_FIELD_PTS, 'Y field name from flow-path points table', parentLayerParameterName=self.DATAPOINTS))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_PTS, 'Output point feature class'))

    def processAlgorithm(self, parameters, context, feedback):
        network_shp = self.parameterAsVectorLayer(parameters, self.NETWORK_SHP, context)
        links_table = self.parameterAsSource(parameters, self.LINKS_TABLE, context)
        rid_field = self.parameterAsString(parameters, self.RID_FIELD, context)
        datapoints = self.parameterAsSource(parameters, self.DATAPOINTS, context)
        output_pts = self.parameterAsOutputLayer(parameters, self.OUTPUT_PTS, context)
        if network_shp is None:
            raise QgsProcessingException('Network feature class is invalid')
        if links_table is None or datapoints is None:
            raise QgsProcessingException('Input table is invalid')
        execute_LocateMostDownstreamPoints(network_shp, links_table, rid_field, datapoints, self.parameterAsString(parameters, self.ID_FIELD_PTS, context), self.parameterAsString(parameters, self.RID_FIELD_PTS, context), self.parameterAsString(parameters, self.DISTANCE_FIELD_PTS, context), self.parameterAsString(parameters, self.X_FIELD_PTS, context), self.parameterAsString(parameters, self.Y_FIELD_PTS, context), output_pts, GIStools=QGIStools, messages=Messages(feedback))
        return {self.OUTPUT_PTS: output_pts}
