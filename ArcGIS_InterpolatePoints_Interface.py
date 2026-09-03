# -*- coding: utf-8 -*-

import arcpy

from InterpolatePoints import execute_InterpolatePoints
import ArcGIStools
from ArcGIS_Messages import Messages


class Toolbox(object):
    def __init__(self):
        self.label = "Large Scale Flood Modeling Toolbox"
        self.alias = ""
        self.tools = [ArcGIS_InterpolatePoints_Interface]


class ArcGIS_InterpolatePoints_Interface(object):
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
            direction="Input",
        )
        param_pts_id_field = arcpy.Parameter(
            displayName="ID field in the data points table",
            name="pts_id_field",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_pts_rid_field = arcpy.Parameter(
            displayName="Route ID field in the data points table",
            name="pts_rid_field",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_pts_distfield = arcpy.Parameter(
            displayName="Distance field in the data points on network layer",
            name="pts_distfield",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_list_fields = arcpy.Parameter(
            displayName="Choose the fields with values to interpolate",
            name="list_fields_to_keep",
            datatype="Field",
            parameterType="Required",
            direction="Input",
            multiValue=True,
        )
        param_targets = arcpy.Parameter(
            displayName="Target points to interpolate on (table)",
            name="targets",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input",
        )
        param_targets_id_field = arcpy.Parameter(
            displayName="ID field in the target points table",
            name="targets_id_field",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_targets_rid_field = arcpy.Parameter(
            displayName="Route ID field in the target points table",
            name="targets_rid_field",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_targets_distfield = arcpy.Parameter(
            displayName="Distance field in the target points on network layer",
            name="targets_distfield",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_routes = arcpy.Parameter(
            displayName="Input route feature class (lines)",
            name="routes",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input",
        )
        param_RID_field = arcpy.Parameter(
            displayName="RID field in routes feature class",
            name="RID_field",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_order_field = arcpy.Parameter(
            displayName="Ordering field in routes feature class",
            name="order_field",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_links = arcpy.Parameter(
            displayName="Routes links",
            name="links",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input",
        )
        param_output_points = arcpy.Parameter(
            displayName="Points Output table",
            name="output_points",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Output",
        )

        param_pts_id_field.parameterDependencies = [param_points_table.name]
        param_pts_rid_field.parameterDependencies = [param_points_table.name]
        param_pts_distfield.parameterDependencies = [param_points_table.name]
        param_list_fields.parameterDependencies = [param_points_table.name]
        param_targets_id_field.parameterDependencies = [param_targets.name]
        param_targets_rid_field.parameterDependencies = [param_targets.name]
        param_targets_distfield.parameterDependencies = [param_targets.name]
        param_RID_field.parameterDependencies = [param_routes.name]
        param_order_field.parameterDependencies = [param_routes.name]

        return [
            param_points_table,
            param_pts_id_field,
            param_pts_rid_field,
            param_pts_distfield,
            param_list_fields,
            param_targets,
            param_targets_id_field,
            param_targets_rid_field,
            param_targets_distfield,
            param_routes,
            param_RID_field,
            param_order_field,
            param_links,
            param_output_points,
        ]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        execute_InterpolatePoints(
            parameters[0].valueAsText,
            parameters[1].valueAsText,
            parameters[2].valueAsText,
            parameters[3].valueAsText,
            _split_multivalue(parameters[4].valueAsText),
            parameters[5].valueAsText,
            parameters[6].valueAsText,
            parameters[7].valueAsText,
            parameters[8].valueAsText,
            parameters[9].valueAsText,
            parameters[12].valueAsText,
            parameters[10].valueAsText,
            parameters[11].valueAsText,
            parameters[13].valueAsText,
            GIStools=ArcGIStools,
            messages=Messages(messages),
        )
        return


def _split_multivalue(value):
    if value in [None, ""]:
        return []
    return [item for item in value.split(";") if item not in [None, ""]]
