# -*- coding: utf-8 -*-

import arcpy

from LocatePointsAlongRoutes import execute_LocatePointsAlongRoutes
import ArcGIStools
from ArcGIS_Messages import Messages


class Toolbox(object):
    def __init__(self):
        self.label = "Large Scale Flood Modeling Toolbox"
        self.alias = ""
        self.tools = [ArcGIS_LocatePointsAlongRoutes_Interface]


class ArcGIS_LocatePointsAlongRoutes_Interface(object):
    def __init__(self):
        self.label = "Project points along Routes"
        self.description = "This tool creates an output table with the projected location of points along a route layer using a common RouteID. The RouteID of each point can be calculated with Relate Network layers tool."
        self.canRunInBackground = True

    def getParameterInfo(self):
        param_points = arcpy.Parameter(
            displayName="Points layer to project",
            name="points",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input",
        )
        param_points_RIDfield = arcpy.Parameter(
            displayName="RouteID field in the points layer",
            name="points_RIDfield",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_routes = arcpy.Parameter(
            displayName="Network layer",
            name="routes",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input",
        )
        param_routes_RIDfield = arcpy.Parameter(
            displayName="RouteID field in the network layer",
            name="routes_RIDfield",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_output = arcpy.Parameter(
            displayName="Output point table",
            name="output",
            datatype="GPTableview",
            parameterType="Required",
            direction="Output",
        )
        param_distance = arcpy.Parameter(
            displayName="Searching distance",
            name="distance",
            datatype="GPDouble",
            parameterType="Required",
            direction="Input",
        )

        param_points_RIDfield.parameterDependencies = [param_points.name]
        param_routes_RIDfield.parameterDependencies = [param_routes.name]

        return [
            param_points,
            param_points_RIDfield,
            param_routes,
            param_routes_RIDfield,
            param_output,
            param_distance,
        ]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        execute_LocatePointsAlongRoutes(
            parameters[0].valueAsText,
            parameters[1].valueAsText,
            parameters[2].valueAsText,
            parameters[3].valueAsText,
            parameters[4].valueAsText,
            float(parameters[5].valueAsText),
            GIStools=ArcGIStools,
            messages=Messages(messages),
        )
        return


LocatePointsAlongRoutes = ArcGIS_LocatePointsAlongRoutes_Interface
