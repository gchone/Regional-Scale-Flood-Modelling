from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parent))
from AssignPointToClosestPointOnRoute import *
import QGIStools
from QGIS_Messages import Messages

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessing
)


class QGIS_AssignPointToClosestPointOnRoute(QgsProcessingAlgorithm):

    POINTS = "POINTS"
    FIELDS_TO_KEEP = "FIELDS_TO_KEEP"
    STAT = "STAT"
    ROUTES = "ROUTES"
    ROUTES_ID_FIELD = "ROUTES_ID_FIELD"
    POINTS_ON_ROUTE = "POINTS_ON_ROUTE"
    POINTS_ON_ROUTE_RID = "POINTS_ON_ROUTE_RID"
    POINTS_ON_ROUTE_DIST = "POINTS_ON_ROUTE_DIST"
    MATCHING_FIELDS_PTS = "MATCHING_FIELDS_PTS"
    MATCHING_FIELDS_TGT = "MATCHING_FIELDS_TGT"
    OUTPUT = "OUTPUT"

    STAT_OPTIONS = ["MEAN", "CLOSEST", "MAX", "2-WAY CLOSEST"]

    def name(self):
        return "assignpointtoclosestpointonroute"

    def displayName(self):
        return "Assign point to closest point on route"

    def group(self):
        return "Large Scale Flood Modelling Toolbox"

    def groupId(self):
        return "large_scale_flood_modelling_toolbox"

    def createInstance(self):
        return QGIS_AssignPointToClosestPointOnRoute()

    def shortHelpString(self):
        return (
            "Assign point to closest point on route\n\n"
            "Projects a point layer to the closest point on a network. "
            "Both input layers (points and points on network) must have a RouteID field.\n"
            "This tool is used at multiple steps in the workflow.\n\n"
            "Inputs:\n"
            "- Points feature class: data points to project (e.g. ws_pathpointsD8, Qpts_spatialized_D8, bathy_on_mainroute)\n"
            "- Fields to keep: fields from data points to transfer to output (e.g. lidar3m_forws, computedQLiDAR, z)\n"
            "- Aggregation method: how to aggregate when multiple data points match a target point (e.g. 2-WAY CLOSEST, CLOSEST, MAX)\n"
            "- Route feature class: oriented route network (e.g. routes_main, routesD4)\n"
            "- RouteID field: RID\n"
            "- Points on route: target points on network (e.g. target_pts, smoothed_pts, pathpointsD4_geom)\n"
            "- RouteID field in target points: RID\n"
            "- Distance field in target points: MEAS or dist\n"
            "- Fields to match in data points: fields used to group matches (e.g. RID, ID_DEM or RID_routesmain, ID_DEM or RID_1)\n"
            "- Fields to match in target points: corresponding fields in target points (e.g. RID, ID_DEM)\n\n"
            "IMPORTANT: The fields to match must be listed in the same order in both layers.\n\n"
            "Output:\n"
            "- Target points with data fields assigned (e.g. Qpts_spatialized, bathy_on_D4)\n"
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessingParameterVectorLayer,
            QgsProcessingParameterField,
            QgsProcessingParameterEnum,
            QgsProcessingParameterFeatureSink,
        )

        self.addParameter(QgsProcessingParameterVectorLayer(
            self.POINTS, "Points feature class (e.g. ws_pathpointsD8, Qpts_spatialized_D8, bathy_on_mainroute)",
            [QgsProcessing.TypeVectorPoint],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.FIELDS_TO_KEEP, "Fields to keep in output (e.g. lidar3m_forws, computedQLiDAR, z)",
            parentLayerParameterName=self.POINTS,
            allowMultiple=True,
        ))
        self.addParameter(QgsProcessingParameterEnum(
            self.STAT, "Aggregation method",
            options=self.STAT_OPTIONS,
            defaultValue=1,
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.ROUTES, "Route feature class (e.g. routes_main, routesD4)",
            [QgsProcessing.TypeVectorLine],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.ROUTES_ID_FIELD, "RouteID field in route feature class",
            parentLayerParameterName=self.ROUTES,
            defaultValue="RID",
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.POINTS_ON_ROUTE, "Points on route (e.g. target_pts, smoothed_pts, pathpointsD4_geom)",
            [QgsProcessing.TypeVectorPoint],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.POINTS_ON_ROUTE_RID, "RouteID field in target points",
            parentLayerParameterName=self.POINTS_ON_ROUTE,
            defaultValue="RID",
        ))
        self.addParameter(QgsProcessingParameterField(
            self.POINTS_ON_ROUTE_DIST, "Distance field in target points (e.g. MEAS, dist)",
            parentLayerParameterName=self.POINTS_ON_ROUTE,
            defaultValue="MEAS",
        ))
        self.addParameter(QgsProcessingParameterField(
            self.MATCHING_FIELDS_PTS,
            "Fields to match in data points (e.g. RID_routesmain, ID_DEM, RID_1 — order matters)",
            parentLayerParameterName=self.POINTS,
            allowMultiple=True,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.MATCHING_FIELDS_TGT, "Fields to match in target points (e.g. RID, ID_DEM — must match order above)",
            parentLayerParameterName=self.POINTS_ON_ROUTE,
            allowMultiple=True,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, "Output points (e.g. Qpts_spatialized, bathy_on_D4)",
        ))

    def processAlgorithm(self, parameters, context, feedback):
        data_layer = self.parameterAsVectorLayer(parameters, self.POINTS, context)
        fields_to_keep = self.parameterAsFields(parameters, self.FIELDS_TO_KEEP, context)
        stat_idx = self.parameterAsEnum(parameters, self.STAT, context)
        stat = self.STAT_OPTIONS[stat_idx]
        routes = self.parameterAsVectorLayer(parameters, self.ROUTES, context)
        rid_field = self.parameterAsString(parameters, self.ROUTES_ID_FIELD, context)
        target_layer = self.parameterAsVectorLayer(parameters, self.POINTS_ON_ROUTE, context)
        target_rid = self.parameterAsString(parameters, self.POINTS_ON_ROUTE_RID, context)
        target_dist = self.parameterAsString(parameters, self.POINTS_ON_ROUTE_DIST, context)
        match_pts = self.parameterAsFields(parameters, self.MATCHING_FIELDS_PTS, context)
        match_tgt = self.parameterAsFields(parameters, self.MATCHING_FIELDS_TGT, context)
        output_path = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)

        if data_layer is None:
            raise QgsProcessingException("Data points layer is invalid")
        if target_layer is None:
            raise QgsProcessingException("Target points layer is invalid")
        if routes is None:
            raise QgsProcessingException("Routes layer is invalid")

        messages = Messages(feedback)
        result = execute_AssignPointToClosestPointOnRoute(
            data_layer,
            fields_to_keep,
            routes,
            rid_field,
            target_layer,
            target_rid,
            target_dist,
            match_pts,
            match_tgt,
            output_path,
            stat,
            QGIStools,
            messages,
        )

        return {self.OUTPUT: result}
