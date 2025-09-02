# -*- coding: utf-8 -*-


#####################################################
# Guénolé Choné
# Date:
# Description: Create Tree from Shapefile
#####################################################

from tree.TreeTools import *

class CreateTreeFromShapefile(object):
    def __init__(self):
        self.label = "Create network from feature class"
        self.description = "This tool creates a river network data structure from a line feature class, defined by a" \
                           " link table and a RouteID."
        self.canRunInBackground = True

    def getParameterInfo(self):
        param_rivernet = arcpy.Parameter(
            displayName="Input feature class (lines)",
            name="rivernet",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_route_shapefile = arcpy.Parameter(
            displayName="Output network layer",
            name="route_shapefile",
            datatype="GPFeatureLayer",
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


        param_routeID_field.parameterDependencies = [param_rivernet.name]
        param_downstream_reach_field.parameterDependencies = [param_rivernet.name]
        param_channeltype_field.parameterDependencies = [param_rivernet.name]

        params = [param_rivernet, param_route_shapefile, param_routelinks_table, param_routeID_field, param_downstream_reach_field, param_channeltype_field]

        return params

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):

        rivernet = parameters[0].valueAsText
        route_shapefile = parameters[1].valueAsText
        routelinks_table = parameters[2].valueAsText
        routeID_field = parameters[3].valueAsText
        downstream_reach_field = parameters[4].valueAsText
        channeltype_field = parameters[5].valueAsText

        execute_CreateTreeFromShapefile(rivernet, route_shapefile, routelinks_table, routeID_field, downstream_reach_field, messages, channeltype_field)

        return
