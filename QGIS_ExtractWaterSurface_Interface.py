from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))

import QGIStools
from QGIS_Messages import Messages
from ExtractWaterSurface import execute_ExtractWaterSurface

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessing,
)


class QGIS_ExtractWaterSurface(QgsProcessingAlgorithm):
    ROUTES = "ROUTES"
    RID_FIELD = "RID_FIELD"
    ORDER_FIELD = "ORDER_FIELD"
    LINKS = "LINKS"
    FROMPOINTS = "FROMPOINTS"
    ROUTES_3M = "ROUTES_3M"
    RID_FIELD_3M = "RID_FIELD_3M"
    LINKS_3M = "LINKS_3M"
    PTS_TABLE = "PTS_TABLE"
    X_FIELD_PTS = "X_FIELD_PTS"
    Y_FIELD_PTS = "Y_FIELD_PTS"
    LIDAR3M_COR = "LIDAR3M_COR"
    DEMS_FOOTPRINTS = "DEMS_FOOTPRINTS"
    DEMS_FIELD = "DEMS_FIELD"
    TARGETS = "TARGETS"
    TARGETS_ID_FIELD = "TARGETS_ID_FIELD"
    TARGETS_RID_FIELD = "TARGETS_RID_FIELD"
    TARGETS_DIST_FIELD = "TARGETS_DIST_FIELD"
    OUT_TABLE = "OUT_TABLE"
    OUTPUT_POINTS = "OUTPUT_POINTS"

    def name(self):
        return "extract_water_surface"

    def displayName(self):
        return "Extract water surface"

    def group(self):
        return "Large Scale Flood Modelling Toolbox"

    def groupId(self):
        return "large_scale_flood_modelling_toolbox"

    def createInstance(self):
        return QGIS_ExtractWaterSurface()

    def shortHelpString(self):
        return (
            "Extract water surface along the main river network by relating the D8 network, "
            "sampling the corrected DEM on D8 path points, interpolating onto target points, "
            "and smoothing the resulting water-surface profile."
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessingParameterVectorLayer,
            QgsProcessingParameterFeatureSource,
            QgsProcessingParameterRasterLayer,
            QgsProcessingParameterField,
            QgsProcessingParameterFeatureSink,
        )

        self.addParameter(QgsProcessingParameterVectorLayer(self.ROUTES, "Input route feature class (lines)", [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterField(self.RID_FIELD, "RouteID field in the Input route feature class", parentLayerParameterName=self.ROUTES, defaultValue="RID"))
        self.addParameter(QgsProcessingParameterField(self.ORDER_FIELD, "Order field in the Input route feature class (from 'Order reaches tool')", parentLayerParameterName=self.ROUTES, defaultValue="Qorder"))
        self.addParameter(QgsProcessingParameterFeatureSource(self.LINKS, "Input route link table", [QgsProcessing.TypeVector]))
        self.addParameter(QgsProcessingParameterVectorLayer(self.FROMPOINTS, "From Points", [QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterVectorLayer(self.ROUTES_3M, "Input routes 3m feature class (lines)", [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterField(self.RID_FIELD_3M, "RouteID field in route 3m feature class", parentLayerParameterName=self.ROUTES_3M, defaultValue="RID"))
        self.addParameter(QgsProcessingParameterFeatureSource(self.LINKS_3M, "Input routes 3m links table", [QgsProcessing.TypeVector]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.PTS_TABLE, "Points table", [QgsProcessing.TypeVector]))
        self.addParameter(QgsProcessingParameterField(self.X_FIELD_PTS, "Name of X field", parentLayerParameterName=self.PTS_TABLE, defaultValue="X"))
        self.addParameter(QgsProcessingParameterField(self.Y_FIELD_PTS, "Name of Y field", parentLayerParameterName=self.PTS_TABLE, defaultValue="Y"))
        self.addParameter(QgsProcessingParameterRasterLayer(self.LIDAR3M_COR, "Lidar 3m cor"))
        self.addParameter(QgsProcessingParameterVectorLayer(self.DEMS_FOOTPRINTS, "DEMs footprint feature class", [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterField(self.DEMS_FIELD, "DEMs field in DEMs footprint feature class", parentLayerParameterName=self.DEMS_FOOTPRINTS, defaultValue="ID_DEM"))
        self.addParameter(QgsProcessingParameterFeatureSource(self.TARGETS, "Target points to extract water surface", [QgsProcessing.TypeVector]))
        self.addParameter(QgsProcessingParameterField(self.TARGETS_ID_FIELD, "ID field in the target points table", parentLayerParameterName=self.TARGETS, defaultValue="ObjectID_1"))
        self.addParameter(QgsProcessingParameterField(self.TARGETS_RID_FIELD, "Route ID field in the target points table", parentLayerParameterName=self.TARGETS, defaultValue="RID"))
        self.addParameter(QgsProcessingParameterField(self.TARGETS_DIST_FIELD, "Distance field in the target points on network layer", parentLayerParameterName=self.TARGETS, defaultValue="MEAS"))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUT_TABLE, "Output: Relate table"))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_POINTS, "Output: Points with extracted water surface"))

    def processAlgorithm(self, parameters, context, feedback):
        routes = self.parameterAsVectorLayer(parameters, self.ROUTES, context)
        rid_field = self.parameterAsString(parameters, self.RID_FIELD, context)
        order_field = self.parameterAsString(parameters, self.ORDER_FIELD, context)
        links = self.parameterAsSource(parameters, self.LINKS, context)
        frompoints = self.parameterAsVectorLayer(parameters, self.FROMPOINTS, context)
        routes_3m = self.parameterAsVectorLayer(parameters, self.ROUTES_3M, context)
        rid_field_3m = self.parameterAsString(parameters, self.RID_FIELD_3M, context)
        links_3m = self.parameterAsSource(parameters, self.LINKS_3M, context)
        pts_table = self.parameterAsSource(parameters, self.PTS_TABLE, context)
        x_field_pts = self.parameterAsString(parameters, self.X_FIELD_PTS, context)
        y_field_pts = self.parameterAsString(parameters, self.Y_FIELD_PTS, context)
        lidar3m_cor = self.parameterAsRasterLayer(parameters, self.LIDAR3M_COR, context)
        dems_footprints = self.parameterAsVectorLayer(parameters, self.DEMS_FOOTPRINTS, context)
        dems_field = self.parameterAsString(parameters, self.DEMS_FIELD, context)
        targets = self.parameterAsSource(parameters, self.TARGETS, context)
        targets_id_field = self.parameterAsString(parameters, self.TARGETS_ID_FIELD, context)
        targets_rid_field = self.parameterAsString(parameters, self.TARGETS_RID_FIELD, context)
        targets_dist_field = self.parameterAsString(parameters, self.TARGETS_DIST_FIELD, context)
        out_table = self.parameterAsOutputLayer(parameters, self.OUT_TABLE, context)
        output_points = self.parameterAsOutputLayer(parameters, self.OUTPUT_POINTS, context)

        if None in [routes, links, frompoints, routes_3m, links_3m, pts_table, lidar3m_cor, dems_footprints, targets]:
            raise QgsProcessingException("One or more input layers are invalid")

        execute_ExtractWaterSurface(
            routes,
            links,
            rid_field,
            order_field,
            frompoints,
            routes_3m,
            rid_field_3m,
            links_3m,
            pts_table,
            x_field_pts,
            y_field_pts,
            lidar3m_cor,
            dems_footprints,
            dems_field,
            targets,
            targets_id_field,
            targets_rid_field,
            targets_dist_field,
            out_table,
            output_points,
            GIStools=QGIStools,
            messages=Messages(feedback),
        )

        return {
            self.OUT_TABLE: out_table,
            self.OUTPUT_POINTS: output_points,
        }


ExtractWaterSurface = QGIS_ExtractWaterSurface
