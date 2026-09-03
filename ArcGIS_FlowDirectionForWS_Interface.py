# -*- coding: utf-8 -*-

import os

import arcpy

from FlowDirectionForWS import execute_FlowDirectionForWS
import ArcGIStools
from ArcGIS_Messages import Messages


class FlowDirForWS(object):
    def __init__(self):
        self.label = "Flow Direction for Water Surface assessment"
        self.description = ""
        self.canRunInBackground = True

    def getParameterInfo(self):
        param_routes = arcpy.Parameter(
            displayName="Input main route feature class (lines)",
            name="routes",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input",
        )
        param_DEM_3m = arcpy.Parameter(
            displayName="DEM for water surface assessment",
            name="DEM_3m",
            datatype="DERasterDataset",
            parameterType="Required",
            direction="Input",
        )
        param_DEMs_footprints = arcpy.Parameter(
            displayName="DEMs footprint feature class",
            name="DEMs_footprints",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input",
        )
        param_output_workspace = arcpy.Parameter(
            displayName="Output workspace",
            name="output_workspace",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input",
        )

        project_path = arcpy.env.workspace
        if project_path not in [None, ""]:
            param_routes.value = os.path.join(project_path, "Geometry.gdb", "routes_main")
            param_DEM_3m.value = os.path.join(project_path, "WaterSurface.gdb", "lidar3m_forws_lakes")
            param_DEMs_footprints.value = os.path.join(project_path, "WaterSurface.gdb", "DEM_footprints")
            param_output_workspace.value = os.path.join(project_path, "WaterSurface.gdb")
        param_routes.filter.list = ["Polyline"]

        return [param_routes, param_DEM_3m, param_DEMs_footprints, param_output_workspace]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        del parameters
        return

    def updateMessages(self, parameters):
        del parameters
        return

    def execute(self, parameters, messages):
        execute_FlowDirectionForWS(
            parameters[0].valueAsText,
            arcpy.Raster(parameters[1].valueAsText),
            parameters[2].valueAsText,
            parameters[3].valueAsText,
            25,
            messages=Messages(messages),
            GIStools=ArcGIStools,
        )
        return


ArcGIS_FlowDirectionForWS_Interface = FlowDirForWS
