import os

import arcpy

import ArcGIStools
from ArcGIS_Messages import Messages
from WidthPostProc import execute_WidthPostProc


class ArcGIS_WidthPostProc_Interface(object):
    def __init__(self):
        self.label = "WidthPostProc"
        self.description = ""
        self.canRunInBackground = True

    def getParameterInfo(self):
        param_network_shp = arcpy.Parameter(
            displayName="Network layer",
            name="network_shp",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input",
        )
        param_RID_field = arcpy.Parameter(
            displayName="RouteID field",
            name="RID_field",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_main_channel_field = arcpy.Parameter(
            displayName="Main channel field",
            name="main_channel_field",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_network_main_only = arcpy.Parameter(
            displayName="Main Network (only) layer",
            name="network_main_only",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input",
        )
        param_RID_field_main = arcpy.Parameter(
            displayName="RouteID field",
            name="RID_field_main",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_network_main_l_field = arcpy.Parameter(
            displayName="Shape_Length field",
            name="network_main_l_field",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_order_field = arcpy.Parameter(
            displayName="Order field",
            name="order_field",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_routes_links = arcpy.Parameter(
            displayName="Full network links table",
            name="routes_links",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input",
        )
        param_network_main_only_links = arcpy.Parameter(
            displayName="Main Network (only) links",
            name="network_main_only_links",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input",
        )
        param_widthdata = arcpy.Parameter(
            displayName="Widthdata layer",
            name="widthdata",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input",
        )
        param_widthid = arcpy.Parameter(
            displayName="CSid",
            name="widthid",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_width_RID_field = arcpy.Parameter(
            displayName="Widthdata layer RID field",
            name="width_RID_field",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_width_distance = arcpy.Parameter(
            displayName="Widthdata layer distance field",
            name="width_distance",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_width_field = arcpy.Parameter(
            displayName="Widthdata layer width field",
            name="width_field",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_datapoints = arcpy.Parameter(
            displayName="Datapoints layer",
            name="datapoints",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input",
        )
        param_id_field_datapts = arcpy.Parameter(
            displayName="Id field in datapoints",
            name="id_field_datapts",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_distance_field_datapts = arcpy.Parameter(
            displayName="MEAS field in datapoints",
            name="distance_field_datapts",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_rid_field_datapts = arcpy.Parameter(
            displayName="RID field in datapoints",
            name="rid_field_datapts",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_output_table = arcpy.Parameter(
            displayName="Output table",
            name="output_table",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output",
        )

        project_path = arcpy.env.workspace
        if project_path not in [None, ""]:
            param_network_shp.value = os.path.join(project_path, "Geometry.gdb", "routes")
            param_network_main_only.value = os.path.join(project_path, "Geometry.gdb", "routes_main")
            param_routes_links.value = os.path.join(project_path, "Geometry.gdb", "routes_links")
            param_network_main_only_links.value = os.path.join(project_path, "Geometry.gdb", "routes_main_links")
            param_widthdata.value = os.path.join(project_path, "Width.gdb", "width_pts")
            param_datapoints.value = os.path.join(project_path, "WaterSurface.gdb", "smoothed_pts")
            param_output_table.value = os.path.join(project_path, "Width.gdb", "width_postpro")

        param_RID_field.parameterDependencies = [param_network_shp.name]
        param_RID_field.value = "RID"
        param_main_channel_field.parameterDependencies = [param_network_shp.name]
        param_main_channel_field.value = "Main"
        param_RID_field_main.parameterDependencies = [param_network_main_only.name]
        param_RID_field_main.value = "RID"
        param_network_main_l_field.parameterDependencies = [param_network_main_only.name]
        param_network_main_l_field.value = "Shape_Length"
        param_order_field.parameterDependencies = [param_network_main_only.name]
        param_order_field.value = "Qorder"
        param_widthid.parameterDependencies = [param_widthdata.name]
        param_widthid.value = "CSid"
        param_width_RID_field.parameterDependencies = [param_widthdata.name]
        param_width_RID_field.value = "RID"
        param_width_distance.parameterDependencies = [param_widthdata.name]
        param_width_distance.value = "Distance_m"
        param_width_field.parameterDependencies = [param_widthdata.name]
        param_width_field.value = "Width_m"
        param_id_field_datapts.parameterDependencies = [param_datapoints.name]
        param_id_field_datapts.value = "ObjectID_1"
        param_distance_field_datapts.parameterDependencies = [param_datapoints.name]
        param_distance_field_datapts.value = "MEAS"
        param_rid_field_datapts.parameterDependencies = [param_datapoints.name]
        param_rid_field_datapts.value = "RID"

        return [
            param_network_shp,
            param_RID_field,
            param_main_channel_field,
            param_network_main_only,
            param_RID_field_main,
            param_network_main_l_field,
            param_order_field,
            param_routes_links,
            param_network_main_only_links,
            param_widthdata,
            param_widthid,
            param_width_RID_field,
            param_width_distance,
            param_width_field,
            param_datapoints,
            param_id_field_datapts,
            param_distance_field_datapts,
            param_rid_field_datapts,
            param_output_table,
        ]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        del parameters
        return

    def updateMessages(self, parameters):
        del parameters
        return

    def execute(self, parameters, messages):
        execute_WidthPostProc(
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
            parameters[12].valueAsText,
            parameters[13].valueAsText,
            parameters[14].valueAsText,
            parameters[15].valueAsText,
            parameters[16].valueAsText,
            parameters[17].valueAsText,
            parameters[18].valueAsText,
            GIStools=ArcGIStools,
            messages=Messages(messages),
        )
        return
