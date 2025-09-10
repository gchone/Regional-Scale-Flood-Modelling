# -*- coding: utf-8 -*-


#####################################################
# Guénolé Choné
# Date: June 2021
# Description: Place points along reaches based on a fixed interval
#####################################################
import arcpy
import os
from tree.TreeTools import *


class PlacePointsAlongReaches(object):
    def __init__(self):
        self.label = "Create points along route feature class"
        self.description = "This tool creates a layer of points on a network based on a fixed interval"
        self.canRunInBackground = True

    def getParameterInfo(self):
        param_network_shp = arcpy.Parameter(
            displayName="Route feature class",
            name="network_shp",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input")
        param_links_table = arcpy.Parameter(
            displayName="Route links table",
            name="links_table",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_RID_field = arcpy.Parameter(
            displayName="RouteID field in Network feature class",
            name="RID_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_interval = arcpy.Parameter(
            displayName="Interval between points, in meters",
            name="interval",
            datatype="GPDouble",
            parameterType="Required",
            direction="Input")
        param_output_pt = arcpy.Parameter(
            displayName="Output: Point table",
            name="output_pt",
            datatype="GPTableView",
            parameterType="Required",
            direction="Output")

        project_path = arcpy.env.workspace

        param_network_shp.filter.list = ["Polyline"]
        param_network_shp.value = os.path.join(project_path, "Geometry.gdb", "routes_main")
        param_links_table.value = os.path.join(project_path, "Geometry.gdb", "routes_main_links")
        param_RID_field.parameterDependencies = [param_network_shp.name]
        param_RID_field.value = "RID"
        param_interval.value = 5.0
        param_output_pt.value = os.path.join(project_path, "Geometry.gdb", "target_pts_raw")

        params = [param_network_shp, param_links_table, param_RID_field, param_interval, param_output_pt]

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
        interval = float(parameters[3].valueAsText)
        output_pt = parameters[4].valueAsText


        execute_PlacePointsAlongReaches(network_shp, links_table, RID_field, interval, output_pt)

        return
