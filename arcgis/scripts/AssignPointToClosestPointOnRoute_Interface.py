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
        param_points = arcpy.Parameter(
            displayName="Points feature class to project (data points)",
            name="points",
            datatype="GPFeatureLayer",
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
            datatype="GPFeatureLayer",
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
            datatype="GPTableView",
            parameterType="Required",
            direction="Output")

        param_list_fields_to_keep.parameterDependencies = [param_points.name]
        param_routesIDfield.parameterDependencies = [param_routes.name]
        param_points_onroute_RIDfield.parameterDependencies = [param_points_onroute.name]
        param_points_onroute_distfield.parameterDependencies = [param_points_onroute.name]
        param_list_fields_matching.parameterDependencies = [param_points.name]
        param_list_fields_matching_target.parameterDependencies = [param_points_onroute.name]
        param_stat.filter.type = "ValueList"
        param_stat.filter.list = ["MEAN", "CLOSEST", "MAX"]
        param_stat.value = "MEAN"
        params = [param_points, param_list_fields_to_keep, param_stat, param_routes,
                  param_routesIDfield, param_points_onroute, param_points_onroute_RIDfield,
                  param_points_onroute_distfield, param_list_fields_matching, param_list_fields_matching_target,
                  param_output_table]

        return params

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):

        points = parameters[0].valueAsText
        list_fields_to_keep = (parameters[1].valueAsText).split(';')
        new_list = [str(item.split('.')[-1]) for item in list_fields_to_keep] #keep only the field name in case it's composed with table_name.field_name
        stat = parameters[2].valueAsText
        routes = parameters[3].valueAsText
        routes_IDfield = parameters[4].valueAsText
        points_onroute = parameters[5].valueAsText
        points_onroute_RIDfield = parameters[6].valueAsText
        points_onroute_distfield = parameters[7].valueAsText
        list_fields_matching = (parameters[8].valueAsText).split(';')
        list_fields_matching_target = (parameters[9].valueAsText).split(';')
        output_table = parameters[10].valueAsText


        execute_AssignPointToClosestPointOnRoute(points, new_list, routes, routes_IDfield,
                                                 points_onroute, points_onroute_RIDfield, points_onroute_distfield,
                                                 list_fields_matching, list_fields_matching_target, output_table, stat)




        return
