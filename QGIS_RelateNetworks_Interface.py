from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))

from RelateNetworks import execute_RelateNetworks
import QGIStools
from QGIS_Messages import Messages

from qgis.core import QgsProcessingAlgorithm, QgsProcessingException, QgsProcessing


class QGIS_RelateNetworks(QgsProcessingAlgorithm):
    SHAPEFILE_A = 'SHAPEFILE_A'
    RID_A = 'RID_A'
    SHAPEFILE_B = 'SHAPEFILE_B'
    RID_B = 'RID_B'
    OUT_TABLE = 'OUT_TABLE'

    def name(self):
        return 'relate_networks'

    def displayName(self):
        return 'Relate network layers'

    def group(self):
        return 'Large Scale Flood Modelling Toolbox - Detailed Tools'

    def groupId(self):
        return 'large_scale_flood_modelling_toolbox_detailed_tools'

    def createInstance(self):
        return QGIS_RelateNetworks()

    def initAlgorithm(self, config=None):
        from qgis.core import QgsProcessingParameterVectorLayer, QgsProcessingParameterField, QgsProcessingParameterFeatureSink
        self.addParameter(QgsProcessingParameterVectorLayer(self.SHAPEFILE_A, 'First network layer', [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterField(self.RID_A, 'RouteID field in the first network layer', parentLayerParameterName=self.SHAPEFILE_A))
        self.addParameter(QgsProcessingParameterVectorLayer(self.SHAPEFILE_B, 'Second network layer', [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterField(self.RID_B, 'RouteID field in the second network layer', parentLayerParameterName=self.SHAPEFILE_B))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUT_TABLE, 'Output table'))

    def processAlgorithm(self, parameters, context, feedback):
        shapefile_a = self.parameterAsVectorLayer(parameters, self.SHAPEFILE_A, context)
        shapefile_b = self.parameterAsVectorLayer(parameters, self.SHAPEFILE_B, context)
        rid_a = self.parameterAsString(parameters, self.RID_A, context)
        rid_b = self.parameterAsString(parameters, self.RID_B, context)
        out_table = self.parameterAsOutputLayer(parameters, self.OUT_TABLE, context)
        if shapefile_a is None or shapefile_b is None:
            raise QgsProcessingException('Network layer is invalid')
        execute_RelateNetworks(shapefile_a, rid_a, shapefile_b, rid_b, out_table, messages=Messages(feedback), GIStools=QGIStools)
        return {self.OUT_TABLE: out_table}
