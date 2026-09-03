# coding: latin-1

import arcpy

from D4FlowDirection import *
import ArcGIStools
from ArcGIS_Messages import Messages


class Toolbox(object):
    def __init__(self):
        self.label = "Large Scale Flood Modeling Toolbox"
        self.alias = ""
        self.tools = [ArcGIS_D4FlowDirection_Interface]


class ArcGIS_D4FlowDirection_Interface(object):
    def __init__(self):
        self.label = "D4 flow direction"
        self.description = "Turn a D8 flow direction into a D4, along a flow path"
        self.canRunInBackground = False

    def getParameterInfo(self):
        param_flowdir = arcpy.Parameter(
            displayName="Flow direction",
            name="flowdir",
            datatype="GPRasterLayer",
            parameterType="Required",
            direction="Input")
        param_dem = arcpy.Parameter(
            displayName="DEM",
            name="dem",
            datatype="GPRasterLayer",
            parameterType="Required",
            direction="Input")
        param_frompoint = arcpy.Parameter(
            displayName="From point",
            name="frompoint",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_d4fd = arcpy.Parameter(
            displayName="Result - D4 Flow direction",
            name="d4fd",
            datatype="GPRasterLayer",
            parameterType="Required",
            direction="Output")
        param_workspace = arcpy.Parameter(
            displayName="Workspace",
            name="in_workspace",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input")

        return [param_flowdir, param_dem, param_frompoint, param_d4fd, param_workspace]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        str_flowdir = parameters[0].valueAsText
        str_dem = parameters[1].valueAsText
        str_frompoint = parameters[2].valueAsText
        save_result = parameters[3].valueAsText
        arcpy.env.scratchWorkspace = parameters[4].valueAsText

        execute_D4FlowDirection(
            arcpy.Raster(str_flowdir),
            arcpy.Raster(str_dem),
            str_frompoint,
            save_result,
            ArcGIStools,
            Messages(messages),
        )
        return
