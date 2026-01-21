# -*- coding: utf-8 -*-


#####################################################
# Guénolé Choné
#####################################################

from FlowDirForWS import *

class FlowDirForWS(object):
    def __init__(self):
        self.label = "Flow Direction for Water Surface assessment"
        self.description = ""
        self.canRunInBackground = True


    def getParameterInfo(self):
        param_routes = arcpy.Parameter(
            displayName="Input main route feature class (lines)",
            name="routes",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_DEM_3m = arcpy.Parameter(
            displayName="DEM for water surface assessment",
            name="DEM_3m",
            datatype="GPRasterLayer",
            parameterType="Required",
            direction="Input")
        param_DEMs_footprints = arcpy.Parameter(
            displayName="DEMs footprint feature class",
            name="DEMs_footprints",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_output_workspace = arcpy.Parameter(
            displayName="Output workspace",
            name="output_workspace",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input")


        params = [param_routes, param_DEM_3m, param_DEMs_footprints, param_output_workspace]


        return params

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):

        routes_main = parameters[0].valueAsText
        DEM3m_forws = arcpy.Raster(parameters[1].valueAsText)
        DEMs_footprints = parameters[2].valueAsText
        output_workspace = parameters[3].valueAsText

        execute_FlowDirForWS(routes_main, DEM3m_forws, DEMs_footprints, output_workspace, 25, messages)

        return
