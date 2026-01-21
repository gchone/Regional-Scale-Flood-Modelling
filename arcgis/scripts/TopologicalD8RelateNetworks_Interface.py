# -*- coding: utf-8 -*-


from tree.TreeTools import *

class TopologicalRelateNetworks(object):
    def __init__(self):
        self.label = "Relate a D8 network layer using topological comparison"
        self.description = "Relate two route layers through a near table"
        self.canRunInBackground = True

    def getParameterInfo(self):

        param_shapefile_A = arcpy.Parameter(
            displayName="D8 network layer",
            name="shapefile_A",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_RID_A = arcpy.Parameter(
            displayName="RouteID field in the D8 network layer",
            name="RID_A",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_links_A = arcpy.Parameter(
            displayName="Input D8 route link table",
            name="links_A",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_shapefile_B = arcpy.Parameter(
            displayName="Reference network layer",
            name="shapefile_B",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_RID_B = arcpy.Parameter(
            displayName="RouteID field in the reference network layer",
            name="RID_B",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_links_B = arcpy.Parameter(
            displayName="Input reference route link table",
            name="links_B",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_fpoints = arcpy.Parameter(
            displayName="From Points",
            name="fpoints",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_out_table = arcpy.Parameter(
            displayName="Output table",
            name="out_table",
            datatype="GPTableView",
            parameterType="Required",
            direction="Output")

        param_RID_A.parameterDependencies = [param_shapefile_A.name]
        param_RID_B.parameterDependencies = [param_shapefile_B.name]

        params = [param_shapefile_A, param_RID_A, param_links_A, param_shapefile_B, param_RID_B, param_links_B, param_fpoints, param_out_table]

        return params

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        routes_A = parameters[0].valueAsText
        RID_A = parameters[1].valueAsText
        links_A = parameters[2].valueAsText
        routes_B = parameters[3].valueAsText
        RID_B = parameters[4].valueAsText
        links_B = parameters[5].valueAsText
        frompoints = parameters[6].valueAsText
        out_table = parameters[7].valueAsText

        execute_CheckNetFitFromUpStream(routes_A, links_A, RID_A, routes_B, links_B, RID_B, frompoints, out_table, messages, "ENDS")

        return
