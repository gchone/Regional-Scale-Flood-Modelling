# -*- coding: utf-8 -*-

#####################################################
# Guénolé Choné
# Date: 11 June 2021
# Description: Locate Mos Downstream Points
#####################################################
import arcpy

from tree.TreeTools import *


class LocateMostDownstreamPoints(object):
    def __init__(self):
        self.label = "Locate most downstream points on network"
        self.description = "This tool creates an output point feature class with the most downstream points of a network"
        self.canRunInBackground = True

    def getParameterInfo(self):
        param_network_shp = arcpy.Parameter(
            displayName="Network feature class",
            name="network_shp",
            datatype="GPFeatureLayer",
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
        param_datapoints = arcpy.Parameter(
            displayName="Flow direction pixels along flow path table",
            name="datapoints",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_id_field_pts = arcpy.Parameter(
            displayName="ID Field name from Flow direction pixels along flow path table",
            name="id_field_pts",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_RID_field_pts = arcpy.Parameter(
            displayName="RouteID field name from Flow direction pixels along flow path table",
            name="RID_field_pts",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_Distance_field_pts = arcpy.Parameter(
            displayName="Name for distance field from Flow direction pixels along flow path table",
            name="Distance_field_pts",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_X_field_pts = arcpy.Parameter(
            displayName="Name for X field from Flow direction pixels along flow path table",
            name="X_field_pts",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_Y_field_pts = arcpy.Parameter(
            displayName="Name for Y field from Flow direction pixels along flow path table",
            name="Y_field_pts",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_output_pts = arcpy.Parameter(
            displayName="Output point feature class",
            name="output_pts",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Output")

        param_RID_field.parameterDependencies = [param_network_shp.name]
        param_id_field_pts.parameterDependencies = [param_datapoints.name]
        param_RID_field_pts.parameterDependencies = [param_datapoints.name]
        param_Distance_field_pts.parameterDependencies = [param_datapoints.name]
        param_X_field_pts.parameterDependencies = [param_datapoints.name]
        param_Y_field_pts.parameterDependencies = [param_datapoints.name]


        params = [param_network_shp, param_links_table, param_RID_field, param_datapoints, param_id_field_pts, param_RID_field_pts, param_Distance_field_pts, param_X_field_pts, param_Y_field_pts, param_output_pts]

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
        datapoints = parameters[3].valueAsText
        id_field_pts = parameters[4].valueAsText
        RID_field_pts = parameters[5].valueAsText
        Distance_field_pts = parameters[6].valueAsText
        X_field_pts = parameters[7].valueAsText
        Y_field_pts = parameters[8].valueAsText
        output_pts = parameters[9].valueAsText

        messages.addMessage(network_shp)
        messages.addMessage(links_table)
        messages.addMessage(RID_field)
        messages.addMessage(datapoints)
        messages.addMessage(id_field_pts)
        messages.addMessage(RID_field_pts)
        messages.addMessage(Distance_field_pts)
        messages.addMessage(X_field_pts)
        messages.addMessage(Y_field_pts)
        messages.addMessage(output_pts)

        execute_LocateMostDownstreamPoints(network_shp, links_table, RID_field, datapoints, id_field_pts, RID_field_pts, Distance_field_pts, X_field_pts, Y_field_pts, output_pts)

        return
