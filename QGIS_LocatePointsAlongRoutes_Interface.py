from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))

from LocatePointsAlongRoutes import execute_LocatePointsAlongRoutes
import QGIStools
from QGIS_Messages import Messages

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessing,
)


class QGIS_LocatePointsAlongRoutes(QgsProcessingAlgorithm):
    POINTS = "POINTS"
    POINTS_RID_FIELD = "POINTS_RID_FIELD"
    ROUTES = "ROUTES"
    ROUTES_RID_FIELD = "ROUTES_RID_FIELD"
    DISTANCE = "DISTANCE"
    OUTPUT = "OUTPUT"

    def name(self):
        return "locate_points_along_routes"

    def displayName(self):
        return "Locate points along routes"

    def group(self):
        return "Large Scale Flood Modelling Toolbox - Detailed Tools"

    def groupId(self):
        return "large_scale_flood_modelling_toolbox_detailed_tools"

    def createInstance(self):
        return QGIS_LocatePointsAlongRoutes()

    def shortHelpString(self):
        return (
            "Locate points along routes\n\n"
            "Locates points along a route network by computing the linear "
            "distance (MEAS) of each point along its corresponding reach. "
            "Points are matched to reaches by RID field.\n\n"
            "Inputs:\n"
            "- Points layer\n"
            "- RID field in the points layer\n"
            "- Routes layer (lines)\n"
            "- RID field in the routes layer\n"
            "- Maximum snap distance (e.g. 10000)\n\n"
            "Output:\n"
            "- Table with all original point attributes plus RID and MEAS fields\n"
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessingParameterFeatureSource,
            QgsProcessingParameterVectorLayer,
            QgsProcessingParameterField,
            QgsProcessingParameterDistance,
            QgsProcessingParameterFeatureSink,
        )

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.POINTS,
                "Points layer",
                [QgsProcessing.TypeVectorPoint],
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.POINTS_RID_FIELD,
                "RID field in the points layer",
                parentLayerParameterName=self.POINTS,
            )
        )
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.ROUTES,
                "Routes layer (lines)",
                [QgsProcessing.TypeVectorLine],
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.ROUTES_RID_FIELD,
                "RID field in the routes layer",
                parentLayerParameterName=self.ROUTES,
            )
        )
        self.addParameter(
            QgsProcessingParameterDistance(
                self.DISTANCE,
                "Maximum snap distance",
                defaultValue=10000.0,
                parentParameterName=self.ROUTES,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                "Output table",
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        points = self.parameterAsSource(parameters, self.POINTS, context)
        points_rid_field = self.parameterAsString(parameters, self.POINTS_RID_FIELD, context)
        routes = self.parameterAsVectorLayer(parameters, self.ROUTES, context)
        routes_rid_field = self.parameterAsString(parameters, self.ROUTES_RID_FIELD, context)
        distance = self.parameterAsDouble(parameters, self.DISTANCE, context)
        output_path = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)

        if points is None:
            raise QgsProcessingException("Points layer is invalid")
        if routes is None:
            raise QgsProcessingException("Routes layer is invalid")

        result = execute_LocatePointsAlongRoutes(
            points,
            points_rid_field,
            routes,
            routes_rid_field,
            output_path,
            distance,
            GIStools=QGIStools,
            messages=Messages(feedback),
        )
        return {self.OUTPUT: result}
