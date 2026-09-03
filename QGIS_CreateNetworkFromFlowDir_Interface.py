from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))

from CreateNetworkFromFlowDir import execute_CreateNetworkFromFlowDir
import QGIStools
from QGIS_Messages import Messages

from qgis.core import QgsProcessingAlgorithm, QgsProcessingException, QgsProcessing


class QGIS_CreateNetworkFromFlowDir(QgsProcessingAlgorithm):
    R_FLOWDIR = 'R_FLOWDIR'
    STR_FROMPOINTS = 'STR_FROMPOINTS'
    ROUTE_SHAPEFILE = 'ROUTE_SHAPEFILE'
    ROUTELINKS_TABLE = 'ROUTELINKS_TABLE'
    ROUTEID_FIELD = 'ROUTEID_FIELD'
    STR_OUTPUT_POINTS = 'STR_OUTPUT_POINTS'
    SPLIT_PTS = 'SPLIT_PTS'
    TOLERANCE = 'TOLERANCE'

    def name(self):
        return 'create_network_from_flowdir'

    def displayName(self):
        return 'Create network from flow direction raster'

    def group(self):
        return 'Large Scale Flood Modelling Toolbox'

    def groupId(self):
        return 'large_scale_flood_modelling_toolbox'

    def createInstance(self):
        return QGIS_CreateNetworkFromFlowDir()

    def initAlgorithm(self, config=None):
        from qgis.core import QgsProcessingParameterRasterLayer, QgsProcessingParameterFeatureSource, QgsProcessingParameterString, QgsProcessingParameterFeatureSink, QgsProcessingParameterNumber
        self.addParameter(QgsProcessingParameterRasterLayer(self.R_FLOWDIR, 'Flow direction raster'))
        self.addParameter(QgsProcessingParameterFeatureSource(self.STR_FROMPOINTS, 'Upstream ends of the network', [QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterString(self.ROUTEID_FIELD, 'RouteID field name', defaultValue='RID'))
        self.addParameter(QgsProcessingParameterFeatureSink(self.ROUTE_SHAPEFILE, 'Output: Network layer'))
        self.addParameter(QgsProcessingParameterFeatureSink(self.ROUTELINKS_TABLE, 'Output: Link table'))
        self.addParameter(QgsProcessingParameterFeatureSink(self.STR_OUTPUT_POINTS, 'Output: Flow direction pixels along flow path output table'))
        self.addParameter(QgsProcessingParameterFeatureSource(self.SPLIT_PTS, 'Split points between reaches', [QgsProcessing.TypeVectorPoint], optional=True))
        self.addParameter(QgsProcessingParameterNumber(self.TOLERANCE, 'Tolerance between split points and the network, in meters', type=QgsProcessingParameterNumber.Double, optional=True, defaultValue=10000.0))

    def processAlgorithm(self, parameters, context, feedback):
        r_flowdir = self.parameterAsRasterLayer(parameters, self.R_FLOWDIR, context)
        str_frompoints = self.parameterAsSource(parameters, self.STR_FROMPOINTS, context)
        route_shapefile = self.parameterAsOutputLayer(parameters, self.ROUTE_SHAPEFILE, context)
        routelinks_table = self.parameterAsOutputLayer(parameters, self.ROUTELINKS_TABLE, context)
        routeID_field = self.parameterAsString(parameters, self.ROUTEID_FIELD, context)
        str_output_points = self.parameterAsOutputLayer(parameters, self.STR_OUTPUT_POINTS, context)
        split_pts = self.parameterAsSource(parameters, self.SPLIT_PTS, context)
        tolerance = self.parameterAsDouble(parameters, self.TOLERANCE, context)
        if r_flowdir is None:
            raise QgsProcessingException('Flow direction raster is invalid')
        if str_frompoints is None:
            raise QgsProcessingException('From points layer is invalid')
        execute_CreateNetworkFromFlowDir(r_flowdir, str_frompoints, route_shapefile, routelinks_table, routeID_field, str_output_points, split_pts, tolerance, GIStools=QGIStools, messages=Messages(feedback))
        return {self.ROUTE_SHAPEFILE: route_shapefile, self.ROUTELINKS_TABLE: routelinks_table, self.STR_OUTPUT_POINTS: str_output_points}
