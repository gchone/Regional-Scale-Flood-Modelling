from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))

from InterpolatePoints import execute_InterpolatePoints
import QGIStools
from QGIS_Messages import Messages

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessing,
)


class QGIS_InterpolatePoints(QgsProcessingAlgorithm):
    POINTS_TABLE = "POINTS_TABLE"
    PTS_ID_FIELD = "PTS_ID_FIELD"
    PTS_RID_FIELD = "PTS_RID_FIELD"
    PTS_DIST_FIELD = "PTS_DIST_FIELD"
    DATA_FIELDS = "DATA_FIELDS"
    TARGETS = "TARGETS"
    TARGETS_ID_FIELD = "TARGETS_ID_FIELD"
    TARGETS_RID_FIELD = "TARGETS_RID_FIELD"
    TARGETS_DIST_FIELD = "TARGETS_DIST_FIELD"
    ROUTES = "ROUTES"
    RID_FIELD = "RID_FIELD"
    ORDER_FIELD = "ORDER_FIELD"
    LINKS = "LINKS"
    OUTPUT = "OUTPUT"

    def name(self):
        return "interpolatepoints"

    def displayName(self):
        return "Interpolate points"

    def group(self):
        return "Large Scale Flood Modelling Toolbox - Detailed Tools"

    def groupId(self):
        return "large_scale_flood_modelling_toolbox_detailed_tools"

    def createInstance(self):
        return QGIS_InterpolatePoints()

    def shortHelpString(self):
        return (
            "Interpolate points\n\n"
            "Interpolates values from data points onto target points along the river network. "
            "Interpolation is done reach by reach, crossing reach boundaries when needed "
            "by looking upstream and downstream for the nearest data points.\n\n"
            "Used in both the width workflow (width_pts → width_postpro) and the "
            "water surface workflow.\n\n"
            "Inputs:\n"
            "- Data points table: points with values to interpolate (e.g. width_pts, bathy_on_D4)\n"
            "- ID field in data points: unique identifier (e.g. id, ObjectID_1)\n"
            "- RID field in data points: RouteID (e.g. RID)\n"
            "- Distance field in data points: MEAS\n"
            "- Fields to interpolate: fields with values to interpolate (e.g. Width, z)\n"
            "- Target points: points to interpolate onto (e.g. smoothed_pts, pathpointsD4)\n"
            "- ID field in target points: unique identifier (e.g. id, ObjectID_1)\n"
            "- RID field in target points: RouteID (e.g. RID)\n"
            "- Distance field in target points: MEAS\n"
            "- Route feature class: oriented route network (e.g. routes_main, routesD4)\n"
            "- RouteID field: RID\n"
            "- Order field: Qorder\n"
            "- Links table: DownID/UpID connectivity (e.g. routes_main_links, linksD4)\n\n"
            "Output:\n"
            "- Target points with interpolated values (e.g. width_postpro, bathy_final)\n"
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessingParameterVectorLayer,
            QgsProcessingParameterField,
            QgsProcessingParameterFeatureSink,
        )

        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.POINTS_TABLE,
                "Data points table (e.g. width_pts, bathy_on_D4)",
                [QgsProcessing.TypeVectorPoint, QgsProcessing.TypeVector],
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.PTS_ID_FIELD,
                "ID field in data points (e.g. id, ObjectID_1)",
                parentLayerParameterName=self.POINTS_TABLE,
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.PTS_RID_FIELD,
                "RID field in data points",
                parentLayerParameterName=self.POINTS_TABLE,
                defaultValue="RID",
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.PTS_DIST_FIELD,
                "Distance field in data points",
                parentLayerParameterName=self.POINTS_TABLE,
                defaultValue="MEAS",
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.DATA_FIELDS,
                "Fields to interpolate (e.g. Width, z)",
                parentLayerParameterName=self.POINTS_TABLE,
                allowMultiple=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.TARGETS,
                "Target points (e.g. smoothed_pts, pathpointsD4)",
                [QgsProcessing.TypeVectorPoint, QgsProcessing.TypeVector],
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.TARGETS_ID_FIELD,
                "ID field in target points (e.g. id, ObjectID_1)",
                parentLayerParameterName=self.TARGETS,
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.TARGETS_RID_FIELD,
                "RID field in target points",
                parentLayerParameterName=self.TARGETS,
                defaultValue="RID",
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.TARGETS_DIST_FIELD,
                "Distance field in target points",
                parentLayerParameterName=self.TARGETS,
                defaultValue="MEAS",
            )
        )
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.ROUTES,
                "Route feature class (e.g. routes_main, routesD4)",
                [QgsProcessing.TypeVectorLine],
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.RID_FIELD,
                "RouteID field",
                parentLayerParameterName=self.ROUTES,
                defaultValue="RID",
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.ORDER_FIELD,
                "Order field",
                parentLayerParameterName=self.ROUTES,
                defaultValue="Qorder",
            )
        )
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.LINKS,
                "Links table (e.g. routes_main_links, linksD4)",
                [QgsProcessing.TypeVector],
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                "Output interpolated points (e.g. width_postpro, bathy_final)",
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        pts_layer = self.parameterAsVectorLayer(parameters, self.POINTS_TABLE, context)
        pts_id = self.parameterAsString(parameters, self.PTS_ID_FIELD, context)
        pts_rid = self.parameterAsString(parameters, self.PTS_RID_FIELD, context)
        pts_dist = self.parameterAsString(parameters, self.PTS_DIST_FIELD, context)
        data_fields = self.parameterAsFields(parameters, self.DATA_FIELDS, context)
        targets_layer = self.parameterAsVectorLayer(parameters, self.TARGETS, context)
        tgt_id = self.parameterAsString(parameters, self.TARGETS_ID_FIELD, context)
        tgt_rid = self.parameterAsString(parameters, self.TARGETS_RID_FIELD, context)
        tgt_dist = self.parameterAsString(parameters, self.TARGETS_DIST_FIELD, context)
        routes = self.parameterAsVectorLayer(parameters, self.ROUTES, context)
        rid_field = self.parameterAsString(parameters, self.RID_FIELD, context)
        order_field = self.parameterAsString(parameters, self.ORDER_FIELD, context)
        links = self.parameterAsVectorLayer(parameters, self.LINKS, context)
        output_path = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)

        if pts_layer is None:
            raise QgsProcessingException("Data points layer is invalid")
        if targets_layer is None:
            raise QgsProcessingException("Target points layer is invalid")
        if routes is None:
            raise QgsProcessingException("Routes layer is invalid")
        if links is None:
            raise QgsProcessingException("Links layer is invalid")

        result = execute_InterpolatePoints(
            pts_layer,
            pts_id,
            pts_rid,
            pts_dist,
            data_fields,
            targets_layer,
            tgt_id,
            tgt_rid,
            tgt_dist,
            routes,
            links,
            rid_field,
            order_field,
            output_path,
            GIStools=QGIStools,
            messages=Messages(feedback),
        )
        return {self.OUTPUT: result}
