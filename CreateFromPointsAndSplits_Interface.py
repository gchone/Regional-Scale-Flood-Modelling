# -*- coding: utf-8 -*-

#####################################################
# Guénolé Choné
# Date: 11 June 2021
# Description: Create From Points and Splits
#####################################################

import arcpy
import os
from tree.TreeTools import *


class CreateFromPointsAndSplits(object):
    def __init__(self):
        self.label = "Create from points and split points"
        self.description = "This tool creates two output layers with the from points and split points along a network."
        self.canRunInBackground = True

    def getParameterInfo(self):
        param_network_shp = arcpy.Parameter(
            displayName="Network feature class",
            name="network_shp",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input")
        param_links_table = arcpy.Parameter(
            displayName="Link table",
            name="links_table",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_RID_field = arcpy.Parameter(
            displayName="RouteID field in the network feature class",
            name="RID_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_points = arcpy.Parameter(
            displayName="Output: From points feature class",
            name="points",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output")
        param_splits = arcpy.Parameter(
            displayName="Output: Split points feature class",
            name="splits",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output")

        project_path = arcpy.env.workspace

        param_network_shp.filter.list = ["Polyline"]
        param_network_shp.value = os.path.join(project_path, "Geometry.gdb", "routes_main")
        param_links_table.value = os.path.join(project_path, "Geometry.gdb", "routes_main_links")
        param_RID_field.parameterDependencies = [param_network_shp.name]
        param_RID_field.value = "RID"
        param_points.value = os.path.join(project_path, "Geometry.gdb", "from_pts")
        param_splits.value = os.path.join(project_path, "Geometry.gdb", "splits")

        params = [param_network_shp, param_links_table, param_RID_field, param_points, param_splits]

        return params

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        network_shp = parameters[0].valueAsText
        links_table = parameters[1].valueAsText
        RID_field = parameters[2].valueAsText
        points = parameters[3].valueAsText
        splits = parameters[4].valueAsText

        execute_CreateFromPointsAndSplits(network_shp, links_table, RID_field, points, splits)

        return
