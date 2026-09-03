from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))

import QGIStools
from QGIS_Messages import Messages
from SpatializeQ import execute_SpatializeQ

from qgis.core import QgsProcessingAlgorithm, QgsProcessingException, QgsProcessing


class QGIS_SpatializeQ(QgsProcessingAlgorithm):
    ROUTE_D8 = 'ROUTE_D8'
    RID_FIELD_D8 = 'RID_FIELD_D8'
    D8PATHPOINTS = 'D8PATHPOINTS'
    RELATE_TABLE = 'RELATE_TABLE'
    R_FLOWACC = 'R_FLOWACC'
    ROUTES = 'ROUTES'
    LINKS = 'LINKS'
    RID_FIELD = 'RID_FIELD'
    QORDER_FIELD = 'QORDER_FIELD'
    QPOINTS = 'QPOINTS'
    ID_FIELD_QPOINTS = 'ID_FIELD_QPOINTS'
    RID_QPOINTS = 'RID_QPOINTS'
    DIST_FIELD_QPOINTS = 'DIST_FIELD_QPOINTS'
    ATLASREACH_FIELD_QPOINTS = 'ATLASREACH_FIELD_QPOINTS'
    TARGETPOINTS = 'TARGETPOINTS'
    ID_FIELD_TARGET = 'ID_FIELD_TARGET'
    RID_FIELD_TARGET = 'RID_FIELD_TARGET'
    DISTANCE_FIELD_TARGET = 'DISTANCE_FIELD_TARGET'
    DEM_FIELD_TARGET = 'DEM_FIELD_TARGET'
    QCSV_FILE = 'QCSV_FILE'
    OUTPUT = 'OUTPUT'

    def name(self):
        return 'spatialize_q'

    def displayName(self):
        return 'SpatializeQ'

    def group(self):
        return 'Large Scale Flood Modelling Toolbox - Detailed Tools'

    def groupId(self):
        return 'large_scale_flood_modelling_toolbox_detailed_tools'

    def createInstance(self):
        return QGIS_SpatializeQ()

    def initAlgorithm(self, config=None):
        from qgis.core import QgsProcessingParameterVectorLayer, QgsProcessingParameterFeatureSource, QgsProcessingParameterField, QgsProcessingParameterRasterLayer, QgsProcessingParameterFile, QgsProcessingParameterFeatureSink
        self.addParameter(QgsProcessingParameterVectorLayer(self.ROUTE_D8, 'Input route D8 feature class (lines)', [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterField(self.RID_FIELD_D8, 'RouteID field', parentLayerParameterName=self.ROUTE_D8, defaultValue='RID'))
        self.addParameter(QgsProcessingParameterVectorLayer(self.D8PATHPOINTS, 'D8 Pathpoints', [QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.RELATE_TABLE, 'Relate table', [QgsProcessing.TypeVector]))
        self.addParameter(QgsProcessingParameterRasterLayer(self.R_FLOWACC, 'Flow Accumulation raster'))
        self.addParameter(QgsProcessingParameterVectorLayer(self.ROUTES, 'Input route feature class (lines)', [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.LINKS, 'Routes links', [QgsProcessing.TypeVector]))
        self.addParameter(QgsProcessingParameterField(self.RID_FIELD, 'RID field in routes feature class', parentLayerParameterName=self.ROUTES, defaultValue='RID'))
        self.addParameter(QgsProcessingParameterField(self.QORDER_FIELD, 'Ordering field in routes feature class', parentLayerParameterName=self.ROUTES, defaultValue='Qorder'))
        self.addParameter(QgsProcessingParameterVectorLayer(self.QPOINTS, 'Qpoints', [QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterField(self.ID_FIELD_QPOINTS, 'Id field in Qpoints', parentLayerParameterName=self.QPOINTS))
        self.addParameter(QgsProcessingParameterField(self.RID_QPOINTS, 'RID field in Qpoints', parentLayerParameterName=self.QPOINTS))
        self.addParameter(QgsProcessingParameterField(self.DIST_FIELD_QPOINTS, 'MEAS field in Qpoints', parentLayerParameterName=self.QPOINTS))
        self.addParameter(QgsProcessingParameterField(self.ATLASREACH_FIELD_QPOINTS, 'AtlasReach field in Qpoints', parentLayerParameterName=self.QPOINTS))
        self.addParameter(QgsProcessingParameterVectorLayer(self.TARGETPOINTS, 'Target points', [QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterField(self.ID_FIELD_TARGET, 'ID field in target points feature class', parentLayerParameterName=self.TARGETPOINTS))
        self.addParameter(QgsProcessingParameterField(self.RID_FIELD_TARGET, 'RID field in target points feature class', parentLayerParameterName=self.TARGETPOINTS))
        self.addParameter(QgsProcessingParameterField(self.DISTANCE_FIELD_TARGET, 'MEAS field in target points feature class', parentLayerParameterName=self.TARGETPOINTS))
        self.addParameter(QgsProcessingParameterField(self.DEM_FIELD_TARGET, 'DEM field in target points feature class', parentLayerParameterName=self.TARGETPOINTS))
        self.addParameter(QgsProcessingParameterFile(self.QCSV_FILE, 'Qcsv_file', behavior=QgsProcessingParameterFile.File, fileFilter='CSV files (*.csv)'))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, 'Points Output table'))

    def processAlgorithm(self, parameters, context, feedback):
        route_D8 = self.parameterAsVectorLayer(parameters, self.ROUTE_D8, context)
        rid_field_D8 = self.parameterAsString(parameters, self.RID_FIELD_D8, context)
        d8_pathpoints = self.parameterAsVectorLayer(parameters, self.D8PATHPOINTS, context)
        relate_table = self.parameterAsSource(parameters, self.RELATE_TABLE, context)
        r_flowacc = self.parameterAsRasterLayer(parameters, self.R_FLOWACC, context)
        routes = self.parameterAsVectorLayer(parameters, self.ROUTES, context)
        links = self.parameterAsSource(parameters, self.LINKS, context)
        rid_field = self.parameterAsString(parameters, self.RID_FIELD, context)
        qorder_field = self.parameterAsString(parameters, self.QORDER_FIELD, context)
        qpoints = self.parameterAsVectorLayer(parameters, self.QPOINTS, context)
        id_field_qpoints = self.parameterAsString(parameters, self.ID_FIELD_QPOINTS, context)
        rid_qpoints = self.parameterAsString(parameters, self.RID_QPOINTS, context)
        dist_field_qpoints = self.parameterAsString(parameters, self.DIST_FIELD_QPOINTS, context)
        atlasreach_field_qpoints = self.parameterAsString(parameters, self.ATLASREACH_FIELD_QPOINTS, context)
        targetpoints = self.parameterAsVectorLayer(parameters, self.TARGETPOINTS, context)
        id_field_target = self.parameterAsString(parameters, self.ID_FIELD_TARGET, context)
        rid_field_target = self.parameterAsString(parameters, self.RID_FIELD_TARGET, context)
        distance_field_target = self.parameterAsString(parameters, self.DISTANCE_FIELD_TARGET, context)
        dem_field_target = self.parameterAsString(parameters, self.DEM_FIELD_TARGET, context)
        qcsv_file = self.parameterAsString(parameters, self.QCSV_FILE, context)
        output_path = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)
        if None in [route_D8, d8_pathpoints, relate_table, r_flowacc, routes, links, qpoints, targetpoints]:
            raise QgsProcessingException('Input layer is invalid')
        result = execute_SpatializeQ(route_D8, rid_field_D8, d8_pathpoints, relate_table, r_flowacc, routes, links, rid_field, qorder_field, qpoints, id_field_qpoints, rid_qpoints, dist_field_qpoints, atlasreach_field_qpoints, targetpoints, id_field_target, rid_field_target, distance_field_target, dem_field_target, qcsv_file, output_path, messages=Messages(feedback), GIStools=QGIStools)
        return {self.OUTPUT: result}
