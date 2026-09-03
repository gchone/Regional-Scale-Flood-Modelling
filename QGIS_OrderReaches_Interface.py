from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))

from OrderReaches import execute_OrderReaches
import QGIStools
from QGIS_Messages import Messages

from qgis.core import QgsProcessingAlgorithm, QgsProcessingException, QgsProcessing


class QGIS_OrderReaches(QgsProcessingAlgorithm):
    ROUTES = 'ROUTES'
    LINKS = 'LINKS'
    RID_FIELD = 'RID_FIELD'
    R_FLOWACC = 'R_FLOWACC'
    ROUTED8 = 'ROUTED8'
    LINKSD8 = 'LINKSD8'
    PTSOND8 = 'PTSOND8'
    RELATETABLE = 'RELATETABLE'
    OUTPUTFIELD = 'OUTPUTFIELD'
    ROUTES_OUT = 'ROUTES_OUT'

    def name(self):
        return 'order_reaches'

    def displayName(self):
        return 'Order reaches'

    def group(self):
        return 'Large Scale Flood Modelling Toolbox - Detailed Tools'

    def groupId(self):
        return 'large_scale_flood_modelling_toolbox_detailed_tools'

    def createInstance(self):
        return QGIS_OrderReaches()

    def initAlgorithm(self, config=None):
        from qgis.core import QgsProcessingParameterVectorLayer, QgsProcessingParameterFeatureSource, QgsProcessingParameterField, QgsProcessingParameterRasterLayer, QgsProcessingParameterString, QgsProcessingParameterFeatureSink
        self.addParameter(QgsProcessingParameterVectorLayer(self.ROUTES, 'routes_main', [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.LINKS, 'routes_main_links', [QgsProcessing.TypeVector]))
        self.addParameter(QgsProcessingParameterField(self.RID_FIELD, 'RID (RouteID field)', parentLayerParameterName=self.ROUTES))
        self.addParameter(QgsProcessingParameterRasterLayer(self.R_FLOWACC, 'lidar10m_facc (flow accumulation raster)'))
        self.addParameter(QgsProcessingParameterVectorLayer(self.ROUTED8, 'routesD8', [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.LINKSD8, 'linksD8', [QgsProcessing.TypeVector]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.PTSOND8, 'pathpointsD8', [QgsProcessing.TypeVector]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.RELATETABLE, 'fd_net_relatetable', [QgsProcessing.TypeVector]))
        self.addParameter(QgsProcessingParameterString(self.OUTPUTFIELD, 'Output field name', defaultValue='Qorder'))
        self.addParameter(QgsProcessingParameterFeatureSink(self.ROUTES_OUT, 'routes_main'))

    def processAlgorithm(self, parameters, context, feedback):
        routes = self.parameterAsVectorLayer(parameters, self.ROUTES, context)
        links = self.parameterAsSource(parameters, self.LINKS, context)
        rid_field = self.parameterAsString(parameters, self.RID_FIELD, context)
        r_flowacc = self.parameterAsRasterLayer(parameters, self.R_FLOWACC, context)
        routeD8 = self.parameterAsVectorLayer(parameters, self.ROUTED8, context)
        linksD8 = self.parameterAsSource(parameters, self.LINKSD8, context)
        ptsonD8 = self.parameterAsSource(parameters, self.PTSOND8, context)
        relatetable = self.parameterAsSource(parameters, self.RELATETABLE, context)
        outputfield = self.parameterAsString(parameters, self.OUTPUTFIELD, context)
        output_path = self.parameterAsOutputLayer(parameters, self.ROUTES_OUT, context)
        if routes is None or links is None or r_flowacc is None or routeD8 is None or linksD8 is None or ptsonD8 is None or relatetable is None:
            raise QgsProcessingException('Input layer is invalid')
        execute_OrderReaches(routes, links, rid_field, r_flowacc, routeD8, linksD8, ptsonD8, relatetable, outputfield, messages=Messages(feedback), GIStools=QGIStools, output_routes=output_path)
        return {self.ROUTES_OUT: output_path}
