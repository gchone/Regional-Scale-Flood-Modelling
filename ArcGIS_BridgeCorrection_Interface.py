# coding: latin-1

import os

import arcpy

from BridgeCorrection import execute_BridgeCorrection
import ArcGIStools
from ArcGIS_Messages import Messages


class BridgeCorrection(object):
    def __init__(self):
        self.label = "Bridges and culverts correction"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        param_raster = arcpy.Parameter(
            displayName="DEM",
            name="raster",
            datatype="DERasterDataset",
            parameterType="Required",
            direction="Input",
        )
        param_bridges = arcpy.Parameter(
            displayName="Bridges to be corrected",
            name="bridges",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input",
        )
        param_res = arcpy.Parameter(
            displayName="Output: Corrected DEM",
            name="result",
            datatype="DERasterDataset",
            parameterType="Required",
            direction="Output",
        )

        project_path = arcpy.env.workspace
        if project_path not in [None, ""]:
            param_raster.value = os.path.join(project_path, "WaterSurface.gdb", "lidar3m_min")
            param_bridges.value = os.path.join(project_path, "Geometry.gdb", "bridges")
            param_res.value = os.path.join(project_path, "WaterSurface.gdb", "lidar3m_forws")
        param_bridges.filter.list = ["Polygon"]

        return [param_raster, param_bridges, param_res]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        del parameters
        return

    def updateMessages(self, parameters):
        del parameters
        return

    def execute(self, parameters, messages):
        execute_BridgeCorrection(
            arcpy.Raster(parameters[0].valueAsText),
            parameters[1].valueAsText,
            parameters[2].valueAsText,
            GIStools=ArcGIStools,
            messages=Messages(messages),
            language="EN",
        )
        return


ArcGIS_BridgeCorrection_Interface = BridgeCorrection
