from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))

import QGIStools
from QGIS_Messages import Messages
from SpatializeQLIDARFromGaugingStations import execute_SpatializeQLIDARFromGaugingStations

from qgis.core import QgsProcessingAlgorithm, QgsProcessingException, QgsProcessing


class QGIS_SpatializeQLIDARFromGaugingStations(QgsProcessingAlgorithm):
    FLOW_ACCUMULATION = 'FLOW_ACCUMULATION'
    ROUTES_D8 = 'ROUTES_D8'
    RID_FIELD_D8 = 'RID_FIELD_D8'
    LINKS_D8 = 'LINKS_D8'
    D8_PATHPOINTS = 'D8_PATHPOINTS'
    Q_STATIONS = 'Q_STATIONS'
    ID_FIELD_Q = 'ID_FIELD_Q'
    NAME_FIELD_Q = 'NAME_FIELD_Q'
    DRAINAGE_FIELD_Q = 'DRAINAGE_FIELD_Q'
    Q_DISTANCE = 'Q_DISTANCE'
    Q_CSV_FILE = 'Q_CSV_FILE'
    DEM_FOOTPRINTS = 'DEM_FOOTPRINTS'
    DEM_ID_FIELD = 'DEM_ID_FIELD'
    BETA = 'BETA'
    RELATETABLE = 'RELATETABLE'
    OUTPUT = 'OUTPUT'

    def name(self):
        return 'spatialize_qlidar_from_gauging_stations'

    def displayName(self):
        return 'Spatialize discharges from gauging stations - Q LiDAR'

    def group(self):
        return 'Large Scale Flood Modelling Toolbox - Detailed Tools'

    def groupId(self):
        return 'large_scale_flood_modelling_toolbox_detailed_tools'

    def createInstance(self):
        return QGIS_SpatializeQLIDARFromGaugingStations()

    def initAlgorithm(self, config=None):
        from qgis.core import QgsProcessingParameterRasterLayer, QgsProcessingParameterVectorLayer, QgsProcessingParameterFeatureSource, QgsProcessingParameterField, QgsProcessingParameterFile, QgsProcessingParameterDistance, QgsProcessingParameterNumber, QgsProcessingParameterFeatureSink
        self.addParameter(QgsProcessingParameterRasterLayer(self.FLOW_ACCUMULATION, 'Flow accumulation (lidar10m_facc)'))
        self.addParameter(QgsProcessingParameterVectorLayer(self.ROUTES_D8, 'D8 route feature class (routesD8)', [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterField(self.RID_FIELD_D8, 'RID field in D8 routes', parentLayerParameterName=self.ROUTES_D8, defaultValue='RID'))
        self.addParameter(QgsProcessingParameterFeatureSource(self.LINKS_D8, 'Routes D8 links (linksD8)', [QgsProcessing.TypeVector]))
        self.addParameter(QgsProcessingParameterVectorLayer(self.D8_PATHPOINTS, 'Point on route D8 (pathpointsD8)', [QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterVectorLayer(self.Q_STATIONS, 'QStations', [QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterField(self.ID_FIELD_Q, 'ID field in gauging stations', parentLayerParameterName=self.Q_STATIONS))
        self.addParameter(QgsProcessingParameterField(self.NAME_FIELD_Q, 'Name field in gauging stations (must match CSV headers)', parentLayerParameterName=self.Q_STATIONS))
        self.addParameter(QgsProcessingParameterField(self.DRAINAGE_FIELD_Q, 'Drainage area field in gauging stations (km²)', parentLayerParameterName=self.Q_STATIONS))
        self.addParameter(QgsProcessingParameterDistance(self.Q_DISTANCE, 'Maximum distance of gauging stations to the river (m)', defaultValue=500.0, parentParameterName=self.ROUTES_D8))
        self.addParameter(QgsProcessingParameterFile(self.Q_CSV_FILE, 'CSV file with discharge measurements', behavior=QgsProcessingParameterFile.File, fileFilter='CSV files (*.csv)'))
        self.addParameter(QgsProcessingParameterVectorLayer(self.DEM_FOOTPRINTS, 'DEM footprints', [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterField(self.DEM_ID_FIELD, 'ID_DEM field in footprints', parentLayerParameterName=self.DEM_FOOTPRINTS))
        self.addParameter(QgsProcessingParameterNumber(self.BETA, 'Beta coefficient (drainage area exponent)', type=QgsProcessingParameterNumber.Double, defaultValue=1.0))
        self.addParameter(QgsProcessingParameterFeatureSource(self.RELATETABLE, 'Relate table - Main routes to D8 correspondence', [QgsProcessing.TypeVector]))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, 'Qpts_spatialized_D8'))

    def processAlgorithm(self, parameters, context, feedback):
        flow_acc = self.parameterAsRasterLayer(parameters, self.FLOW_ACCUMULATION, context)
        routes_d8 = self.parameterAsVectorLayer(parameters, self.ROUTES_D8, context)
        rid_field_d8 = self.parameterAsString(parameters, self.RID_FIELD_D8, context)
        links_d8 = self.parameterAsSource(parameters, self.LINKS_D8, context)
        d8_pathpoints = self.parameterAsVectorLayer(parameters, self.D8_PATHPOINTS, context)
        q_stations = self.parameterAsVectorLayer(parameters, self.Q_STATIONS, context)
        id_field_q = self.parameterAsString(parameters, self.ID_FIELD_Q, context)
        name_field_q = self.parameterAsString(parameters, self.NAME_FIELD_Q, context)
        drainage_field_q = self.parameterAsString(parameters, self.DRAINAGE_FIELD_Q, context)
        q_distance = self.parameterAsDouble(parameters, self.Q_DISTANCE, context)
        csv_file = self.parameterAsString(parameters, self.Q_CSV_FILE, context)
        dem_footprints = self.parameterAsVectorLayer(parameters, self.DEM_FOOTPRINTS, context)
        dem_id_field = self.parameterAsString(parameters, self.DEM_ID_FIELD, context)
        beta = self.parameterAsDouble(parameters, self.BETA, context)
        relatetable = self.parameterAsSource(parameters, self.RELATETABLE, context)
        output_path = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)
        if None in [flow_acc, routes_d8, links_d8, d8_pathpoints, q_stations, dem_footprints, relatetable]:
            raise QgsProcessingException('One or more input layers are invalid')
        result = execute_SpatializeQLIDARFromGaugingStations(routes_d8, links_d8, rid_field_d8, d8_pathpoints, flow_acc, q_stations, id_field_q, name_field_q, drainage_field_q, q_distance, csv_file, dem_footprints, dem_id_field, beta, relatetable, output_path, messages=Messages(feedback), GIStools=QGIStools)
        return {self.OUTPUT: result}
