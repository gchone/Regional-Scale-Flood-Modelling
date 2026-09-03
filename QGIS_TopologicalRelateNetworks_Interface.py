from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))

from TopologicalRelateNetworks import execute_TopologicalRelateNetworks
import QGIStools
from QGIS_Messages import Messages

from qgis.core import QgsProcessingAlgorithm, QgsProcessingException, QgsProcessing


class QGIS_TopologicalRelateNetworks(QgsProcessingAlgorithm):
    ROUTES_A = 'ROUTES_A'
    LINKS_A = 'LINKS_A'
    RID_A = 'RID_A'
    ROUTES_B = 'ROUTES_B'
    LINKS_B = 'LINKS_B'
    RID_B = 'RID_B'
    FROMPOINTS = 'FROMPOINTS'
    OUT_TABLE = 'OUT_TABLE'

    def name(self):
        return 'topological_relate_networks'

    def displayName(self):
        return 'Relate a D8 network layer using topological comparison'

    def group(self):
        return 'Large Scale Flood Modelling Toolbox - Detailed Tools'

    def groupId(self):
        return 'large_scale_flood_modelling_toolbox_detailed_tools'

    def createInstance(self):
        return QGIS_TopologicalRelateNetworks()

    def initAlgorithm(self, config=None):
        from qgis.core import QgsProcessingParameterVectorLayer, QgsProcessingParameterFeatureSource, QgsProcessingParameterField, QgsProcessingParameterFeatureSink
        self.addParameter(QgsProcessingParameterVectorLayer(self.ROUTES_A, 'D8 network layer', [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterField(self.RID_A, 'RouteID field in the D8 network layer', parentLayerParameterName=self.ROUTES_A))
        self.addParameter(QgsProcessingParameterFeatureSource(self.LINKS_A, 'Input D8 route link table', [QgsProcessing.TypeVector]))
        self.addParameter(QgsProcessingParameterVectorLayer(self.ROUTES_B, 'Reference network layer', [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterField(self.RID_B, 'RouteID field in the reference network layer', parentLayerParameterName=self.ROUTES_B))
        self.addParameter(QgsProcessingParameterFeatureSource(self.LINKS_B, 'Input reference route link table', [QgsProcessing.TypeVector]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.FROMPOINTS, 'From points', [QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUT_TABLE, 'Output table'))

    def processAlgorithm(self, parameters, context, feedback):
        routes_a = self.parameterAsVectorLayer(parameters, self.ROUTES_A, context)
        links_a = self.parameterAsSource(parameters, self.LINKS_A, context)
        rid_a = self.parameterAsString(parameters, self.RID_A, context)
        routes_b = self.parameterAsVectorLayer(parameters, self.ROUTES_B, context)
        links_b = self.parameterAsSource(parameters, self.LINKS_B, context)
        rid_b = self.parameterAsString(parameters, self.RID_B, context)
        frompoints = self.parameterAsSource(parameters, self.FROMPOINTS, context)
        out_table = self.parameterAsOutputLayer(parameters, self.OUT_TABLE, context)
        if routes_a is None or routes_b is None or links_a is None or links_b is None or frompoints is None:
            raise QgsProcessingException('Input layer is invalid')
        execute_TopologicalRelateNetworks(routes_a, links_a, rid_a, routes_b, links_b, rid_b, frompoints, out_table, messages=Messages(feedback), GIStools=QGIStools, final_selection='ENDS')
        return {self.OUT_TABLE: out_table}
