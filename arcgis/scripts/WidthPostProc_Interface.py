# -*- coding: utf-8 -*-


#####################################################
# Guénolé Choné
# Date: August 2021
# Description: WidthPostProc
#####################################################


from WidthAssessment import *

class WidthPostProc(object):
    def __init__(self):
        self.label = "WidthPostProc"
        self.description = ""
        self.canRunInBackground = True

    def getParameterInfo(self):

        param_network_shp = arcpy.Parameter(
            displayName="Network layer",
            name="network_shp",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_RID_field = arcpy.Parameter(
            displayName="RouteID field",
            name="RID_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_main_channel_field = arcpy.Parameter(
            displayName="Main channel field",
            name="main_channel_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_network_main_only = arcpy.Parameter(
            displayName="Main Network (only) layer",
            name="network_main_only",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_RID_field_main = arcpy.Parameter(
            displayName="RouteID field",
            name="RID_field_main",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_network_main_l_field = arcpy.Parameter(
            displayName="Shape_Length field",
            name="network_main_l_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_order_field = arcpy.Parameter(
            displayName="Order field",
            name="order_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_network_main_only_links = arcpy.Parameter(
            displayName="Main Network (only) links",
            name="network_main_only_links",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_widthdata = arcpy.Parameter(
            displayName="Widthdata layer",
            name="widthdata",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_widthid = arcpy.Parameter(
            displayName="CSid",
            name="widthid",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_width_RID_field = arcpy.Parameter(
            displayName="Widthdata layer RID field",
            name="width_RID_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_width_distance = arcpy.Parameter(
            displayName="Widthdata layer distance field",
            name="width_distance",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_width_field = arcpy.Parameter(
            displayName="Widthdata layer width field",
            name="width_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_datapoints = arcpy.Parameter(
            displayName="Datapoints layer",
            name="datapoints",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_id_field_datapts = arcpy.Parameter(
            displayName="Id field in datapoints",
            name="id_field_datapts",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_distance_field_datapts = arcpy.Parameter(
            displayName="MEAS field in datapoints",
            name="distance_field_datapts",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_rid_field_datapts = arcpy.Parameter(
            displayName="RID field in datapoints",
            name="rid_field_datapts",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_output_table = arcpy.Parameter(
            displayName="Output table",
            name="output_table",
            datatype="GPTableView",
            parameterType="Required",
            direction="Output")

        param_RID_field.parameterDependencies = [param_network_shp.name]
        param_main_channel_field.parameterDependencies = [param_network_shp.name]
        param_RID_field_main.parameterDependencies = [param_network_main_only.name]
        param_network_main_l_field.parameterDependencies = [param_network_main_only.name]
        param_order_field.parameterDependencies = [param_network_main_only.name]
        param_widthid.parameterDependencies = [param_widthdata.name]
        param_width_RID_field.parameterDependencies = [param_widthdata.name]
        param_width_distance.parameterDependencies = [param_widthdata.name]
        param_width_field.parameterDependencies = [param_widthdata.name]
        param_id_field_datapts.parameterDependencies = [param_datapoints.name]
        param_distance_field_datapts.parameterDependencies = [param_datapoints.name]
        param_rid_field_datapts.parameterDependencies = [param_datapoints.name]

        params = [param_network_shp, param_RID_field, param_main_channel_field, param_network_main_only, param_RID_field_main, param_network_main_l_field, param_order_field, param_network_main_only_links, param_widthdata, param_widthid, param_width_RID_field, param_width_distance, param_width_field, param_datapoints, param_id_field_datapts, param_distance_field_datapts, param_rid_field_datapts, param_output_table]

        return params

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        network_shp = parameters[0].valueAsText
        RID_field = parameters[1].valueAsText
        main_channel_field = parameters[2].valueAsText
        network_main_only = parameters[3].valueAsText
        RID_field_main = parameters[4].valueAsText
        network_main_l_field = parameters[5].valueAsText
        order_field = parameters[6].valueAsText
        network_main_only_links = parameters[7].valueAsText
        widthdata = parameters[8].valueAsText
        widthid = parameters[9].valueAsText
        width_RID_field = parameters[10].valueAsText
        width_distance = parameters[11].valueAsText
        width_field = parameters[12].valueAsText
        datapoints = parameters[13].valueAsText
        id_field_datapts = parameters[14].valueAsText
        distance_field_datapts = parameters[15].valueAsText
        rid_field_datapts = parameters[16].valueAsText
        output_table = parameters[17].valueAsText

        execute_WidthPostProc(network_shp, RID_field, main_channel_field, network_main_only, RID_field_main, network_main_l_field, order_field, network_main_only_links, widthdata, widthid, width_RID_field, width_distance, width_field, datapoints, id_field_datapts, distance_field_datapts, rid_field_datapts, output_table, messages)

        return
