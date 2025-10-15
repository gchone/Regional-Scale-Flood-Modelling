# -*- coding: utf-8 -*-


#####################################################
# Guénolé Choné
# Date: 10 June 2021
# Description: Assign points to the closest point on the Route
#####################################################
import arcpy

from AssignPointToClosestPointOnRoute import *

class AssignPointToClosestPointOnRoute(object):
    def __init__(self):
        self.label = "Project point to the closest point on the network"
        self.description = """This tool creates an output feature class  by projecting a point layer to the closest\
        point on a network. Both input layers (points and points on network) MUST have the RouteID field)."""

        self.canRunInBackground = True

    def getParameterInfo(self):
        param_config = arcpy.Parameter(
            displayName="Configuration",
            name="config",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        param_points = arcpy.Parameter(
            displayName="Points feature class to project (data points)",
            name="points",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input")
        param_list_fields_to_keep = arcpy.Parameter(
            displayName="Choose the fields to keep in the output",
            name="list_fields_to_keep",
            datatype="Field",
            parameterType="Required",
            direction="Input",
            multiValue = True)
        param_list_fields_matching = arcpy.Parameter(
            displayName="Fields to match in the data points",
            name="list_fields_matching",
            datatype="Field",
            parameterType="Required",
            direction="Input",
            multiValue = True)
        param_stat = arcpy.Parameter(
            displayName="Average data or take only the data from the closest data point",
            name="stat",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        param_routes = arcpy.Parameter(
            displayName="Route feature class",
            name="routes",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input")
        param_routesIDfield = arcpy.Parameter(
            displayName="RouteID field from the route feature class",
            name="routesIDfield",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_points_onroute = arcpy.Parameter(
            displayName="Points layer on network (target points)",
            name="points_onroute",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_points_onroute_RIDfield = arcpy.Parameter(
            displayName="RouteID field in the points on network layer",
            name="points_onroute_RIDfield",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_points_onroute_distfield = arcpy.Parameter(
            displayName="Distance field in the points on network layer",
            name="points_onroute_distfield",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_list_fields_matching_target = arcpy.Parameter(
            displayName="Fields to match in the target points",
            name="z_field",
            datatype="Field",
            parameterType="Required",
            direction="Input",
            multiValue = True)
        param_output_table = arcpy.Parameter(
            displayName="Output point layer",
            name="output_shp",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output")

        project_path = arcpy.env.workspace

        param_config.filter.type = "ValueList"
        param_config.filter.list = ["LiDAR discharge", "Bathymetry to D4", "Width to D4"]
        param_config.value = "LiDAR discharge"

        param_points.filter.list = ["Point"]
        param_points.value = os.path.join(project_path, "Discharge.gdb", "Qpts_spatialized_D8")

        param_list_fields_to_keep.parameterDependencies = [param_points.name]
        param_list_fields_to_keep.value = "computedQLiDAR"

        param_stat.filter.type = "ValueList"
        param_stat.filter.list = ["MEAN", "CLOSEST", "MAX"]
        param_stat.value = "MEAN"

        param_routes.filter.list = ["Polyline"]
        param_routes.value = os.path.join(project_path, "Geometry.gdb", "routes_main")
        param_routesIDfield.parameterDependencies = [param_routes.name]
        param_routesIDfield.value = "RID"
        param_points_onroute.value = os.path.join(project_path, "WaterSurface.gdb", "smoothed_pts")
        param_points_onroute_RIDfield.parameterDependencies = [param_points_onroute.name]
        param_points_onroute_RIDfield.value = "RID"
        param_points_onroute_distfield.parameterDependencies = [param_points_onroute.name]
        param_points_onroute_distfield.value = "MEAS"
        param_list_fields_matching.parameterDependencies = [param_points.name]
        param_list_fields_matching_target.parameterDependencies = [param_points_onroute.name]
        param_list_fields_matching.value = "RID_routesmain;ID_DEM"
        param_list_fields_matching_target.value = "RID;ID_DEM"
        param_output_table.value = os.path.join(project_path, "Discharge.gdb", "Qpts_spatialized")

        params = [param_config,param_points, param_list_fields_to_keep, param_stat, param_routes,
                  param_routesIDfield, param_points_onroute, param_points_onroute_RIDfield,
                  param_points_onroute_distfield, param_list_fields_matching, param_list_fields_matching_target,
                  param_output_table]

        return params

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        project_path = arcpy.env.workspace
        if not parameters[0].hasBeenValidated:
            if parameters[0].valueAsText == "LiDAR discharge":
                parameters[1].value = os.path.join(project_path, "Discharge.gdb", "Qpts_spatialized_D8")
                parameters[2].value = "computedQLiDAR"
                parameters[3].value = "MEAN"
                parameters[4].value = os.path.join(project_path, "Geometry.gdb", "routes_main")
                parameters[5].value = "RID"
                parameters[6].value = os.path.join(project_path, "WaterSurface.gdb", "smoothed_pts")
                parameters[7].value = "RID"
                parameters[8].value = "MEAS"
                parameters[9].value = "RID_routesmain;ID_DEM"
                parameters[10].value = "RID;ID_DEM"
                parameters[11].value = os.path.join(project_path, "Discharge.gdb", "Qpts_spatialized")

            if parameters[0].valueAsText == "Bathymetry to D4":
                parameters[1].value = os.path.join(project_path, "Lisflood_inputs.gdb", "bathy_on_mainroute")
                parameters[2].value = "z"
                parameters[3].value = "MAX"
                parameters[4].value = os.path.join(project_path, "Lisflood_inputs.gdb", "routesD4")
                parameters[5].value = "RID"
                parameters[6].value = os.path.join(project_path, "Lisflood_inputs.gdb", "pathpointsD4")
                parameters[7].value = "RID"
                parameters[8].value = "dist"
                parameters[9].value = "RID_D4"
                parameters[10].value = "RID"
                parameters[11].value = os.path.join(project_path, "Lisflood_inputs.gdb", "bathy_on_D4")

            if parameters[0].valueAsText == "Width to D4":
                parameters[1].value = os.path.join(project_path, "Lisflood_inputs.gdb", "width_on_mainroute")
                parameters[2].value = "Width_m"
                parameters[3].value = "MEAN"
                parameters[4].value = os.path.join(project_path, "Lisflood_inputs.gdb", "routesD4")
                parameters[5].value = "RID"
                parameters[6].value = os.path.join(project_path, "Lisflood_inputs.gdb", "pathpointsD4")
                parameters[7].value = "RID"
                parameters[8].value = "dist"
                parameters[9].value = "RID_D4"
                parameters[10].value = "RID"
                parameters[11].value = os.path.join(project_path, "Lisflood_inputs.gdb", "width_on_D4")
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):

        points = parameters[1].valueAsText
        list_fields_to_keep = (parameters[2].valueAsText).split(';')
        new_list = [str(item.split('.')[-1]) for item in list_fields_to_keep] #keep only the field name in case it's composed with table_name.field_name
        stat = parameters[3].valueAsText
        routes = parameters[4].valueAsText
        routes_IDfield = parameters[5].valueAsText
        points_onroute = parameters[6].valueAsText
        points_onroute_RIDfield = parameters[7].valueAsText
        points_onroute_distfield = parameters[8].valueAsText
        list_fields_matching = (parameters[9].valueAsText).split(';')
        list_fields_matching_target = (parameters[10].valueAsText).split(';')
        output_table = parameters[11].valueAsText


        execute_AssignPointToClosestPointOnRoute(points, new_list, routes, routes_IDfield,
                                                 points_onroute, points_onroute_RIDfield, points_onroute_distfield,
                                                 list_fields_matching, list_fields_matching_target, output_table, stat)




        return
