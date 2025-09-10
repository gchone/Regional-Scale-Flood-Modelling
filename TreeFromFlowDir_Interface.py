# -*- coding: utf-8 -*-


#####################################################
# Guénolé Choné
# Date: 11 June 2021
# Description: Create Tree from Flow Direction raster
#####################################################
from tree.TreeTools import *


class TreeFromFlowDir(object):
    def __init__(self):
        self.label = "Create network from flow direction raster"
        self.description = "This tool creates a network data structure from a flow direction raster, defined by a " \
                           "link  atablend a RouteID field."
        self.canRunInBackground = True

    def getParameterInfo(self):
        param_r_flowdir = arcpy.Parameter(
            displayName="Flow direction raster",
            name="r_flowdir",
            datatype="DERasterDataset",
            parameterType="Required",
            direction="Input")
        param_str_frompoints = arcpy.Parameter(
            displayName="Upstream ends of the network (points layer)",
            name="str_frompoints",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input")
        param_route_shapefile = arcpy.Parameter(
            displayName="Output: Network layer",
            name="route_shapefile",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output")
        param_routelinks_table = arcpy.Parameter(
            displayName="Output: Link table",
            name="routelinks_table",
            datatype="GPTableView",
            parameterType="Required",
            direction="Output")
        param_routeID_field = arcpy.Parameter(
            displayName="RouteID field name",
            name="routeID_field",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        param_str_output_points = arcpy.Parameter(
            displayName="Output: Flow direction pixels along flow path output table",
            name="str_output_points",
            datatype="GPTableView",
            parameterType="Required",
            direction="Output")
        param_split_pts = arcpy.Parameter(
            displayName="Split points between reaches (feature class)",
            name="split_pts",
            datatype="DEFeatureClass",
            parameterType="Optional",
            direction="Input")
        param_tolerance = arcpy.Parameter(
            displayName="Tolerance between split points and the network, in meters",
            name="tolerance",
            datatype="GPDouble",
            parameterType="Optional",
            direction="Input")

        project_path = arcpy.env.workspace

        param_r_flowdir.value = os.path.join(project_path, "WaterSurface.gdb", "lidar3m_fd")
        param_str_frompoints.value = os.path.join(project_path, "Geometry.gdb", "from_pts")
        param_route_shapefile.value = os.path.join(project_path, "WaterSurface.gdb", "wsroutesD8")
        param_routelinks_table.value = os.path.join(project_path, "WaterSurface.gdb", "wslinksD8")
        param_routeID_field.value = "RID"
        param_str_output_points.value = os.path.join(project_path, "WaterSurface.gdb", "ws_pathpointsD8")

        params = [param_r_flowdir, param_str_frompoints, param_route_shapefile, param_routelinks_table, param_routeID_field, param_str_output_points, param_split_pts, param_tolerance]

        return params

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):

        r_flowdir = arcpy.Raster(parameters[0].valueAsText)
        str_frompoints = parameters[1].valueAsText
        route_shapefile = parameters[2].valueAsText
        routelinks_table = parameters[3].valueAsText
        routeID_field = parameters[4].valueAsText
        str_output_points = parameters[5].valueAsText
        split_pts = parameters[6].valueAsText
        tolerance = parameters[7].valueAsText

        execute_TreeFromFlowDir(r_flowdir, str_frompoints, route_shapefile, routelinks_table, routeID_field, str_output_points, messages, split_pts, tolerance)

        return
