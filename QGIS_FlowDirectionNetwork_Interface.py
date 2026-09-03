from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))

from FlowDirectionNetwork import execute_FlowDirectionNetwork
import QGIStools
from QGIS_Messages import Messages

from qgis.core import QgsProcessingAlgorithm, QgsProcessingException, QgsProcessing


class QGIS_FlowDirectionNetwork(QgsProcessingAlgorithm):
    ROUTES = 'ROUTES'
    LINKS = 'LINKS'
    RID_FIELD = 'RID_FIELD'
    R_FLOW_DIR = 'R_FLOW_DIR'
    ROUTED8 = 'ROUTED8'
    LINKSD8 = 'LINKSD8'
    PTSOND8 = 'PTSOND8'
    RELATETABLE = 'RELATETABLE'

    def name(self):
        return 'flow_direction_network'

    def displayName(self):
        return 'Flow Direction Network'

    def group(self):
        return 'Large Scale Flood Modelling Toolbox - Detailed Tools'

    def groupId(self):
        return 'large_scale_flood_modelling_toolbox_detailed_tools'

    def createInstance(self):
        return QGIS_FlowDirectionNetwork()

    def initAlgorithm(self, config=None):
        from qgis.core import QgsProcessingParameterVectorLayer, QgsProcessingParameterFeatureSource, QgsProcessingParameterField, QgsProcessingParameterRasterLayer, QgsProcessingParameterFeatureSink
        self.addParameter(QgsProcessingParameterVectorLayer(self.ROUTES, 'Input route feature class', [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.LINKS, 'Link table', [QgsProcessing.TypeVector]))
        self.addParameter(QgsProcessingParameterField(self.RID_FIELD, 'RouteID field', parentLayerParameterName=self.ROUTES))
        self.addParameter(QgsProcessingParameterRasterLayer(self.R_FLOW_DIR, 'Flow direction raster'))
        self.addParameter(QgsProcessingParameterFeatureSink(self.ROUTED8, 'Output: Route D8 feature class'))
        self.addParameter(QgsProcessingParameterFeatureSink(self.LINKSD8, 'Output: Link table'))
        self.addParameter(QgsProcessingParameterFeatureSink(self.PTSOND8, 'Output: Point on route D8 feature class'))
        self.addParameter(QgsProcessingParameterFeatureSink(self.RELATETABLE, 'Output: Relate table'))

    def processAlgorithm(self, parameters, context, feedback):
        routes = self.parameterAsVectorLayer(parameters, self.ROUTES, context)
        links = self.parameterAsSource(parameters, self.LINKS, context)
        rid_field = self.parameterAsString(parameters, self.RID_FIELD, context)
        r_flow_dir = self.parameterAsRasterLayer(parameters, self.R_FLOW_DIR, context)
        routeD8 = self.parameterAsOutputLayer(parameters, self.ROUTED8, context)
        linksD8 = self.parameterAsOutputLayer(parameters, self.LINKSD8, context)
        ptsonD8 = self.parameterAsOutputLayer(parameters, self.PTSOND8, context)
        relatetable = self.parameterAsOutputLayer(parameters, self.RELATETABLE, context)
        if routes is None or links is None or r_flow_dir is None:
            raise QgsProcessingException('Input layer is invalid')
        execute_FlowDirectionNetwork(routes, links, rid_field, r_flow_dir, routeD8, linksD8, ptsonD8, relatetable, messages=Messages(feedback), GIStools=QGIStools)
        return {self.ROUTED8: routeD8, self.LINKSD8: linksD8, self.PTSOND8: ptsonD8, self.RELATETABLE: relatetable}
