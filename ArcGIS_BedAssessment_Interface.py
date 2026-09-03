# -*- coding: utf-8 -*-

import arcpy
import os

from BedAssessment import *
import ArcGIStools
from ArcGIS_Messages import Messages


class Toolbox(object):
    def __init__(self):
        self.label = "Large Scale Flood Modeling Toolbox"
        self.alias = ""
        self.tools = [ArcGIS_BedAssessment_Interface]


class ArcGIS_BedAssessment_Interface(object):
    def __init__(self):
        self.label = "Bed Assessment"
        self.description = ""
        self.canRunInBackground = True

    def getParameterInfo(self):
        param_route = arcpy.Parameter(
            displayName="Route layer",
            name="route",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_route_RID_field = arcpy.Parameter(
            displayName="RouteID field",
            name="route_RID_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_route_order_field = arcpy.Parameter(
            displayName="Route Order field",
            name="route_order_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_routelinks = arcpy.Parameter(
            displayName="Route links",
            name="routelinks",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_points = arcpy.Parameter(
            displayName="Points",
            name="points",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_points_IDfield = arcpy.Parameter(
            displayName="Id field in datapoints",
            name="points_IDfield",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_points_RIDfield = arcpy.Parameter(
            displayName="RID field in datapoints",
            name="points_RIDfield",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_points_distfield = arcpy.Parameter(
            displayName="MEAS field in datapoints",
            name="points_distfield",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_points_Qfield = arcpy.Parameter(
            displayName="Q field",
            name="points_Qfield",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_points_Wfield = arcpy.Parameter(
            displayName="W field",
            name="points_Wfield",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_points_WSfield = arcpy.Parameter(
            displayName="WS field",
            name="points_WSfield",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_points_DEMfield = arcpy.Parameter(
            displayName="DEM field",
            name="points_DEMfield",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_manning = arcpy.Parameter(
            displayName="Manning coefficient",
            name="manning",
            datatype="GPDouble",
            parameterType="Required",
            direction="Input")
        param_min_slope = arcpy.Parameter(
            displayName="Minimum energy slope in flat areas",
            name="min_slope",
            datatype="GPDouble",
            parameterType="Required",
            direction="Input")
        param_output_pts = arcpy.Parameter(
            displayName="Output table",
            name="output_pts",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output")

        project_path = arcpy.env.workspace
        param_route.value = os.path.join(project_path, "Geometry.gdb", "routes_main")
        param_route_RID_field.parameterDependencies = [param_route.name]
        param_route_RID_field.value = "RID"
        param_route_order_field.parameterDependencies = [param_route.name]
        param_route_order_field.value = "Qorder"
        param_routelinks.value = os.path.join(project_path, "Geometry.gdb", "routes_main_links")
        param_points.value = os.path.join(project_path, "Bathy.gdb", "bathy_input_pts")
        param_points_IDfield.parameterDependencies = [param_points.name]
        param_points_IDfield.value = "ObjectID_1"
        param_points_RIDfield.parameterDependencies = [param_points.name]
        param_points_RIDfield.value = "RID"
        param_points_distfield.parameterDependencies = [param_points.name]
        param_points_distfield.value = "MEAS"
        param_points_Qfield.parameterDependencies = [param_points.name]
        param_points_Qfield.value = "computedQLiDAR"
        param_points_Wfield.parameterDependencies = [param_points.name]
        param_points_Wfield.value = "Width_m"
        param_points_WSfield.parameterDependencies = [param_points.name]
        param_points_WSfield.value = "zws_smoothed"
        param_points_DEMfield.parameterDependencies = [param_points.name]
        param_points_DEMfield.value = "ID_DEM"
        param_manning.value = 0.03
        param_min_slope.value = 0.00001
        param_output_pts.value = os.path.join(project_path, "Bathy.gdb", "bathy_pts")

        return [
            param_route,
            param_route_RID_field,
            param_route_order_field,
            param_routelinks,
            param_points,
            param_points_IDfield,
            param_points_RIDfield,
            param_points_distfield,
            param_points_Qfield,
            param_points_Wfield,
            param_points_WSfield,
            param_points_DEMfield,
            param_manning,
            param_min_slope,
            param_output_pts,
        ]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        execute_BedAssessment(
            parameters[0].valueAsText,
            parameters[1].valueAsText,
            parameters[2].valueAsText,
            parameters[3].valueAsText,
            parameters[4].valueAsText,
            parameters[5].valueAsText,
            parameters[6].valueAsText,
            parameters[7].valueAsText,
            parameters[8].valueAsText,
            parameters[9].valueAsText,
            parameters[10].valueAsText,
            parameters[11].valueAsText,
            float(parameters[12].valueAsText),
            float(parameters[13].valueAsText),
            parameters[14].valueAsText,
            ArcGIStools,
            Messages(messages),
        )
        return
