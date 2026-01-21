# -*- coding: utf-8 -*-

from InterpolatePoints import *

class InterpolatePoints(object):
    def __init__(self):
        self.label = "Interpolate points"
        self.description = ""
        self.canRunInBackground = True

    def getParameterInfo(self):

        param_points_table = arcpy.Parameter(
            displayName="Data points (table)",
            name="points_table",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_pts_id_field = arcpy.Parameter(
            displayName="ID field in the data points table",
            name="pts_id_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_pts_rid_field = arcpy.Parameter(
            displayName="Route ID field in the data points table",
            name="pts_rid_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_pts_distfield = arcpy.Parameter(
            displayName="Distance field in the data points on network layer",
            name="pts_distfield",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_list_fields = arcpy.Parameter(
            displayName="Choose the fields with values to interpolate",
            name="list_fields_to_keep",
            datatype="Field",
            parameterType="Required",
            direction="Input",
            multiValue=True)
        param_targets = arcpy.Parameter(
            displayName="Target points to interpolate on (table)",
            name="targets",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_targets_id_field = arcpy.Parameter(
            displayName="ID field in the target points table",
            name="targets_id_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_targets_rid_field = arcpy.Parameter(
            displayName="Route ID field in the target points table",
            name="targets_rid_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_targets_distfield = arcpy.Parameter(
            displayName="Distance field in the target points on network layer",
            name="targets_distfield",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_routes = arcpy.Parameter(
            displayName="Input route feature class (lines)",
            name="routes",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_RID_field = arcpy.Parameter(
            displayName="RID field in routes feature class",
            name="RID_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_order_field = arcpy.Parameter(
            displayName="Ordering field in routes feature class",
            name="order_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_links = arcpy.Parameter(
            displayName="Routes links",
            name="links",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_output_points = arcpy.Parameter(
            displayName="Points Output table",
            name="output_points",
            datatype="GPTableView",
            parameterType="Required",
            direction="Output")

        param_pts_id_field.parameterDependencies = [param_points_table.name]
        param_pts_rid_field.parameterDependencies = [param_points_table.name]
        param_pts_distfield.parameterDependencies = [param_points_table.name]
        param_list_fields.parameterDependencies = [param_points_table.name]
        param_targets_id_field.parameterDependencies = [param_targets.name]
        param_targets_rid_field.parameterDependencies = [param_targets.name]
        param_targets_distfield.parameterDependencies = [param_targets.name]
        param_RID_field.parameterDependencies = [param_routes.name]
        param_order_field.parameterDependencies = [param_routes.name]

        params = [param_points_table, param_pts_id_field, param_pts_rid_field, param_pts_distfield, param_list_fields,
                  param_targets, param_targets_id_field, param_targets_rid_field, param_targets_distfield, param_routes,
                  param_RID_field, param_order_field, param_links, param_output_points]

        return params

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):

        points_table = parameters[0].valueAsText
        id_field_pts = parameters[1].valueAsText
        RID_field_pts = parameters[2].valueAsText
        Distance_field_pts = parameters[3].valueAsText
        list_fields = (parameters[4].valueAsText).split(';')
        data_fields = [str(item) for item in list_fields]
        targetpoints = parameters[5].valueAsText
        id_field_target = parameters[6].valueAsText
        RID_field_target = parameters[7].valueAsText
        Distance_field_target = parameters[8].valueAsText
        network_shp = parameters[9].valueAsText
        network_RID_field = parameters[10].valueAsText
        order_field = parameters[11].valueAsText
        links_table= parameters[12].valueAsText
        ouput_table = parameters[13].valueAsText

        execute_InterpolatePoints(points_table, id_field_pts, RID_field_pts, Distance_field_pts, data_fields,
                                  targetpoints, id_field_target, RID_field_target, Distance_field_target, network_shp,
                                  links_table, network_RID_field, order_field, ouput_table)

        return
