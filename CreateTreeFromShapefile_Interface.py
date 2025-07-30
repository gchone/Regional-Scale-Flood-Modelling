# -*- coding: utf-8 -*-


#####################################################
# Guénolé Choné
# Date:
# Description: Create Tree from Shapefile
#####################################################

import os
import arcpy
from tree.TreeTools import *

class CreateTreeFromShapefile(object):
    def __init__(self):
        self.label = "Create network from feature class"
        self.description = "This tool creates a river network data structure from a line feature class, defined by a" \
                           " link table and a RouteID."
        self.canRunInBackground = True

    def getParameterInfo(self):
        param_config = arcpy.Parameter(
            displayName="Configuration",
            name="config",
            datatype="GPString",
            parameterType="Required",
            direction="Input")

        param_rivernet = arcpy.Parameter(
            displayName="Input feature class (lines)",
            name="rivernet",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input")
        param_route_shapefile = arcpy.Parameter(
            displayName="Output network layer",
            name="route_shapefile",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output")
        param_routelinks_table = arcpy.Parameter(
            displayName="Output link table (DownRouteID-UpRouteID)",
            name="routelinks_table",
            datatype="GPTableView",
            parameterType="Required",
            direction="Output")
        param_routeID_field = arcpy.Parameter(
            displayName="RouteID field",
            name="routeID_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_downstream_reach_field = arcpy.Parameter(
            displayName="Field identifying the most downstream reach",
            name="downstream_reach_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_channeltype_field = arcpy.Parameter(
            displayName="Field identifying the main or secondary channel",
            name="channeltype_field",
            datatype="Field",
            parameterType="Optional",
            direction="Input")

        current_project = arcpy.mp.ArcGISProject("CURRENT")
        project_path =  os.path.dirname(current_project.filePath)

        param_config.filter.type = "ValueList"
        param_config.filter.list = ["Main channel only", "With secondary channels"]
        param_config.value = "With secondary channels"

        param_rivernet.value = os.path.join(project_path, "Geometry.gdb", "linear_net_d")
        param_rivernet.filter.list = ["Polyline"]
        param_routeID_field.parameterDependencies = [param_rivernet.name]
        param_routeID_field.value = "RID"
        param_downstream_reach_field.parameterDependencies = [param_rivernet.name]
        param_downstream_reach_field.value = "DownEnd"
        param_channeltype_field.parameterDependencies = [param_rivernet.name]
        param_channeltype_field.value = "Main"
        param_route_shapefile.value = os.path.join(project_path, "Geometry.gdb", "routes")
        param_routelinks_table.value = os.path.join(project_path, "Geometry.gdb", "routes_links")

        param_rivernet.category = "Parameters"
        param_routeID_field.category = "Parameters"
        param_downstream_reach_field.category = "Parameters"
        param_channeltype_field.category = "Parameters"
        param_route_shapefile.category = "Parameters"
        param_routelinks_table.category = "Parameters"

        params = [param_config, param_rivernet, param_route_shapefile, param_routelinks_table, param_routeID_field, param_downstream_reach_field, param_channeltype_field]

        return params

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        current_project = arcpy.mp.ArcGISProject("CURRENT")
        project_path = os.path.dirname(current_project.filePath)
        if not parameters[0].hasBeenValidated:
            if parameters[0].valueAsText == "Main channel only":
                parameters[1].value = os.path.join(project_path, "Geometry.gdb", "linear_main_d")
                parameters[4].value = "RID"
                parameters[5].value = "DownEnd"
                parameters[6].value = None
                parameters[2].value = os.path.join(project_path, "Geometry.gdb", "routes_main")
                parameters[3].value = os.path.join(project_path, "Geometry.gdb", "routes_main_links")
            if parameters[0].valueAsText == "With secondary channels":
                parameters[1].value = os.path.join(project_path, "Geometry.gdb", "linear_net_d")
                parameters[4].value = "RID"
                parameters[5].value = "DownEnd"
                parameters[6].value = "Main"
                parameters[2].value = os.path.join(project_path, "Geometry.gdb", "routes")
                parameters[3].value = os.path.join(project_path, "Geometry.gdb", "routes_links")



        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):

        rivernet = parameters[1].valueAsText
        route_shapefile = parameters[2].valueAsText
        routelinks_table = parameters[3].valueAsText
        routeID_field = parameters[4].valueAsText
        downstream_reach_field = parameters[5].valueAsText
        channeltype_field = parameters[6].valueAsText

        execute_CreateTreeFromShapefile(rivernet, route_shapefile, routelinks_table, routeID_field, downstream_reach_field, messages, channeltype_field)

        return
