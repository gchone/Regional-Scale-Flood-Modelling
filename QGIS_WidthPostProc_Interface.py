from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))

import QGIStools
from QGIS_Messages import Messages
from WidthPostProc import execute_WidthPostProc

from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
)


class QGIS_WidthPostProc(QgsProcessingAlgorithm):
    NETWORK_SHP = "NETWORK_SHP"
    RID_FIELD = "RID_FIELD"
    MAIN_CHANNEL_FIELD = "MAIN_CHANNEL_FIELD"
    NETWORK_MAIN_ONLY = "NETWORK_MAIN_ONLY"
    RID_FIELD_MAIN = "RID_FIELD_MAIN"
    NETWORK_MAIN_L_FIELD = "NETWORK_MAIN_L_FIELD"
    ORDER_FIELD = "ORDER_FIELD"
    ROUTES_LINKS = "ROUTES_LINKS"
    NETWORK_MAIN_ONLY_LINKS = "NETWORK_MAIN_ONLY_LINKS"
    WIDTHDATA = "WIDTHDATA"
    WIDTHID = "WIDTHID"
    WIDTH_RID_FIELD = "WIDTH_RID_FIELD"
    WIDTH_DISTANCE = "WIDTH_DISTANCE"
    WIDTH_FIELD = "WIDTH_FIELD"
    DATAPOINTS = "DATAPOINTS"
    ID_FIELD_DATAPTS = "ID_FIELD_DATAPTS"
    DISTANCE_FIELD_DATAPTS = "DISTANCE_FIELD_DATAPTS"
    RID_FIELD_DATAPTS = "RID_FIELD_DATAPTS"
    OUTPUT_TABLE = "OUTPUT_TABLE"

    def name(self):
        return "width_post_proc"

    def displayName(self):
        return "Width post-processing"

    def group(self):
        return "Large Scale Flood Modelling Toolbox"

    def groupId(self):
        return "large_scale_flood_modelling_toolbox"

    def createInstance(self):
        return QGIS_WidthPostProc()

    def shortHelpString(self):
        return (
            "Project WidthByCrossSections width points from the split network onto the main-channel "
            "network, interpolate the main-channel widths to target points, then add projected "
            "secondary-channel contributions before materializing the final point output."
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessingParameterFeatureSink,
            QgsProcessingParameterFeatureSource,
            QgsProcessingParameterField,
            QgsProcessingParameterVectorLayer,
        )

        self.addParameter(QgsProcessingParameterVectorLayer(self.NETWORK_SHP, "Network layer", [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterField(self.RID_FIELD, "RouteID field", parentLayerParameterName=self.NETWORK_SHP, defaultValue="RID"))
        self.addParameter(QgsProcessingParameterField(self.MAIN_CHANNEL_FIELD, "Main channel field", parentLayerParameterName=self.NETWORK_SHP, defaultValue="Main"))
        self.addParameter(QgsProcessingParameterVectorLayer(self.NETWORK_MAIN_ONLY, "Main Network (only) layer", [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterField(self.RID_FIELD_MAIN, "RouteID field", parentLayerParameterName=self.NETWORK_MAIN_ONLY, defaultValue="RID"))
        self.addParameter(QgsProcessingParameterField(self.NETWORK_MAIN_L_FIELD, "Shape_Length field", parentLayerParameterName=self.NETWORK_MAIN_ONLY, defaultValue="Shape_Length"))
        self.addParameter(QgsProcessingParameterField(self.ORDER_FIELD, "Order field", parentLayerParameterName=self.NETWORK_MAIN_ONLY, defaultValue="Qorder"))
        self.addParameter(QgsProcessingParameterFeatureSource(self.ROUTES_LINKS, "Full network links table", [QgsProcessing.TypeVector]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.NETWORK_MAIN_ONLY_LINKS, "Main Network (only) links", [QgsProcessing.TypeVector]))
        self.addParameter(QgsProcessingParameterVectorLayer(self.WIDTHDATA, "Widthdata layer", [QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterField(self.WIDTHID, "CSid", parentLayerParameterName=self.WIDTHDATA, defaultValue="CSid"))
        self.addParameter(QgsProcessingParameterField(self.WIDTH_RID_FIELD, "Widthdata layer RID field", parentLayerParameterName=self.WIDTHDATA, defaultValue="RID"))
        self.addParameter(QgsProcessingParameterField(self.WIDTH_DISTANCE, "Widthdata layer distance field", parentLayerParameterName=self.WIDTHDATA, defaultValue="Distance_m"))
        self.addParameter(QgsProcessingParameterField(self.WIDTH_FIELD, "Widthdata layer width field", parentLayerParameterName=self.WIDTHDATA, defaultValue="Width_m"))
        self.addParameter(QgsProcessingParameterFeatureSource(self.DATAPOINTS, "Datapoints layer", [QgsProcessing.TypeVector]))
        self.addParameter(QgsProcessingParameterField(self.ID_FIELD_DATAPTS, "Id field in datapoints", parentLayerParameterName=self.DATAPOINTS, defaultValue="ObjectID_1"))
        self.addParameter(QgsProcessingParameterField(self.DISTANCE_FIELD_DATAPTS, "MEAS field in datapoints", parentLayerParameterName=self.DATAPOINTS, defaultValue="MEAS"))
        self.addParameter(QgsProcessingParameterField(self.RID_FIELD_DATAPTS, "RID field in datapoints", parentLayerParameterName=self.DATAPOINTS, defaultValue="RID"))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_TABLE, "Output table"))

    def processAlgorithm(self, parameters, context, feedback):
        network_shp = self.parameterAsVectorLayer(parameters, self.NETWORK_SHP, context)
        rid_field = self.parameterAsString(parameters, self.RID_FIELD, context)
        main_channel_field = self.parameterAsString(parameters, self.MAIN_CHANNEL_FIELD, context)
        network_main_only = self.parameterAsVectorLayer(parameters, self.NETWORK_MAIN_ONLY, context)
        rid_field_main = self.parameterAsString(parameters, self.RID_FIELD_MAIN, context)
        network_main_l_field = self.parameterAsString(parameters, self.NETWORK_MAIN_L_FIELD, context)
        order_field = self.parameterAsString(parameters, self.ORDER_FIELD, context)
        routes_links = self.parameterAsSource(parameters, self.ROUTES_LINKS, context)
        network_main_only_links = self.parameterAsSource(parameters, self.NETWORK_MAIN_ONLY_LINKS, context)
        widthdata = self.parameterAsVectorLayer(parameters, self.WIDTHDATA, context)
        widthid = self.parameterAsString(parameters, self.WIDTHID, context)
        width_rid_field = self.parameterAsString(parameters, self.WIDTH_RID_FIELD, context)
        width_distance = self.parameterAsString(parameters, self.WIDTH_DISTANCE, context)
        width_field = self.parameterAsString(parameters, self.WIDTH_FIELD, context)
        datapoints = self.parameterAsSource(parameters, self.DATAPOINTS, context)
        id_field_datapts = self.parameterAsString(parameters, self.ID_FIELD_DATAPTS, context)
        distance_field_datapts = self.parameterAsString(parameters, self.DISTANCE_FIELD_DATAPTS, context)
        rid_field_datapts = self.parameterAsString(parameters, self.RID_FIELD_DATAPTS, context)
        output_table = self.parameterAsOutputLayer(parameters, self.OUTPUT_TABLE, context)

        if None in [network_shp, network_main_only, routes_links, network_main_only_links, widthdata, datapoints]:
            raise QgsProcessingException("One or more input layers are invalid")

        execute_WidthPostProc(
            network_shp,
            rid_field,
            main_channel_field,
            network_main_only,
            rid_field_main,
            network_main_l_field,
            order_field,
            routes_links,
            network_main_only_links,
            widthdata,
            widthid,
            width_rid_field,
            width_distance,
            width_field,
            datapoints,
            id_field_datapts,
            distance_field_datapts,
            rid_field_datapts,
            output_table,
            GIStools=QGIStools,
            messages=Messages(feedback),
        )
        return {self.OUTPUT_TABLE: output_table}
