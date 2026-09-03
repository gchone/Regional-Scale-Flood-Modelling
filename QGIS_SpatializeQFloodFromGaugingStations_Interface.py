from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))

import QGIStools
from QGIS_Messages import Messages
from SpatializeQFloodFromGaugingStations import execute_SpatializeQFloodFromGaugingStations

from qgis.core import QgsProcessingAlgorithm, QgsProcessingException, QgsProcessing


class QGIS_SpatializeQFloodFromGaugingStations(QgsProcessingAlgorithm):
    FLOWACC = 'FLOWACC'
    ROUTES = 'ROUTES'
    RID_FIELD = 'RID_FIELD'
    LINKS = 'LINKS'
    PATHPOINTS = 'PATHPOINTS'
    QSTATIONS = 'QSTATIONS'
    ID_FIELD_Q = 'ID_FIELD_Q'
    NAME_FIELD_Q = 'NAME_FIELD_Q'
    DRAINAGE_FIELD_Q = 'DRAINAGE_FIELD_Q'
    Q_DISTANCE = 'Q_DISTANCE'
    Q_FIELD_Q = 'Q_FIELD_Q'
    BETA = 'BETA'
    OUTPUT = 'OUTPUT'

    def name(self):
        return 'spatialize_qflood_from_gauging_stations'

    def displayName(self):
        return 'Spatialize discharges from gauging stations - Flood discharge'

    def group(self):
        return 'Large Scale Flood Modelling Toolbox - Detailed Tools'

    def groupId(self):
        return 'large_scale_flood_modelling_toolbox_detailed_tools'

    def createInstance(self):
        return QGIS_SpatializeQFloodFromGaugingStations()

    def initAlgorithm(self, config=None):
        from qgis.core import QgsProcessingParameterRasterLayer, QgsProcessingParameterVectorLayer, QgsProcessingParameterFeatureSource, QgsProcessingParameterField, QgsProcessingParameterDistance, QgsProcessingParameterNumber, QgsProcessingParameterFeatureSink
        self.addParameter(QgsProcessingParameterRasterLayer(self.FLOWACC, 'Flow accumulation (lidar10m_facc)'))
        self.addParameter(QgsProcessingParameterVectorLayer(self.ROUTES, 'D8 route feature class (routesD8)', [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterField(self.RID_FIELD, 'RID field in routes (RID)', parentLayerParameterName=self.ROUTES, defaultValue='RID'))
        self.addParameter(QgsProcessingParameterFeatureSource(self.LINKS, 'Routes D8 links (linksD8)', [QgsProcessing.TypeVector]))
        self.addParameter(QgsProcessingParameterVectorLayer(self.PATHPOINTS, 'Point on route D8 (pathpointsD8)', [QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterVectorLayer(self.QSTATIONS, 'Qstations', [QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterField(self.ID_FIELD_Q, 'Id field in Qstations', parentLayerParameterName=self.QSTATIONS))
        self.addParameter(QgsProcessingParameterField(self.NAME_FIELD_Q, 'Gauging station name in Qstations', parentLayerParameterName=self.QSTATIONS))
        self.addParameter(QgsProcessingParameterField(self.DRAINAGE_FIELD_Q, 'Drainage area in Qstations', parentLayerParameterName=self.QSTATIONS))
        self.addParameter(QgsProcessingParameterDistance(self.Q_DISTANCE, 'Maximum distance of gauging stations to the river (m)', defaultValue=500.0, parentParameterName=self.ROUTES))
        self.addParameter(QgsProcessingParameterField(self.Q_FIELD_Q, 'Discharge field in Qstations', parentLayerParameterName=self.QSTATIONS))
        self.addParameter(QgsProcessingParameterNumber(self.BETA, 'Beta coefficient', type=QgsProcessingParameterNumber.Double, defaultValue=1.0))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, 'Points Output table (suggested name: Qflood_D8)'))

    def processAlgorithm(self, parameters, context, feedback):
        flowacc = self.parameterAsRasterLayer(parameters, self.FLOWACC, context)
        routes = self.parameterAsVectorLayer(parameters, self.ROUTES, context)
        rid_field = self.parameterAsString(parameters, self.RID_FIELD, context)
        links = self.parameterAsSource(parameters, self.LINKS, context)
        pathpoints = self.parameterAsVectorLayer(parameters, self.PATHPOINTS, context)
        q_stations = self.parameterAsVectorLayer(parameters, self.QSTATIONS, context)
        id_field_q = self.parameterAsString(parameters, self.ID_FIELD_Q, context)
        name_field_q = self.parameterAsString(parameters, self.NAME_FIELD_Q, context)
        drainage_field_q = self.parameterAsString(parameters, self.DRAINAGE_FIELD_Q, context)
        q_distance = self.parameterAsDouble(parameters, self.Q_DISTANCE, context)
        q_field_q = self.parameterAsString(parameters, self.Q_FIELD_Q, context)
        beta = self.parameterAsDouble(parameters, self.BETA, context)
        output_path = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)
        if None in [flowacc, routes, links, pathpoints, q_stations]:
            raise QgsProcessingException('One or more input layers are invalid')
        result = execute_SpatializeQFloodFromGaugingStations(routes, links, rid_field, pathpoints, flowacc, q_stations, id_field_q, name_field_q, drainage_field_q, q_distance, q_field_q, beta, output_path, messages=Messages(feedback), GIStools=QGIStools)
        return {self.OUTPUT: result}
