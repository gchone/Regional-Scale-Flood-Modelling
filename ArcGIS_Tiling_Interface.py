# coding: latin-1

import arcpy
import os

from Tiling import execute_create_zones
import ArcGIStools
from ArcGIS_Messages import Messages


class Toolbox(object):
    def __init__(self):
        self.label = "Large Scale Flood Modeling Toolbox"
        self.alias = ""
        self.tools = [CreateZonesWlakes]


class CreateZonesWlakes(object):
    def __init__(self):
        self.label = "Tiling"
        self.description = "Define independent zones (tiles) for hydraulic simulations with LISFLOOD-FP"
        self.canRunInBackground = False

    def getParameterInfo(self):
        param_flowdir = arcpy.Parameter(
            displayName="Flow direction",
            name="flowdir",
            datatype="GPRasterLayer",
            parameterType="Required",
            direction="Input")
        param_lakes = arcpy.Parameter(
            displayName="Lakes",
            name="lakes",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_frompoint = arcpy.Parameter(
            displayName="Upstream extremities (From points)",
            name="frompoint",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_distance = arcpy.Parameter(
            displayName="Tiles length (m)",
            name="distance",
            datatype="GPLong",
            parameterType="Required",
            direction="Input")
        param_bufferw = arcpy.Parameter(
            displayName="Tiles minimum width (m)",
            name="bufferw",
            datatype="GPLong",
            parameterType="Required",
            direction="Input")
        param_folder = arcpy.Parameter(
            displayName="Tiles folder",
            name="folder ",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input")
        param_workspace = arcpy.Parameter(
            displayName="Workspace",
            name="in_workspace",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input")

        param_workspace.filter.list = ["File System"]
        param_lakes.filter.list = ["POLYGON"]
        param_frompoint.filter.list = ["Point"]

        project_root = arcpy.env.workspace
        if project_root not in [None, ""]:
            param_flowdir.value = os.path.join(project_root, "10mDEMs.gdb", "lidar10m_fd")
            param_lakes.value = os.path.join(project_root, "Geometry.gdb", "lakesforsim")
            param_frompoint.value = os.path.join(project_root, "Geometry.gdb", "from_pts")
            param_folder.value = os.path.join(project_root, "Tiles")
            param_workspace.value = os.path.join(project_root, "temp")

        param_distance.value = 15000
        param_bufferw.value = 3000

        return [param_flowdir, param_lakes, param_frompoint, param_distance, param_bufferw, param_folder, param_workspace]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        del parameters
        return

    def updateMessages(self, parameters):
        del parameters
        return

    def execute(self, parameters, messages):
        flowdir_raster = arcpy.Raster(parameters[0].valueAsText)
        lakes = parameters[1].valueAsText
        frompoint = parameters[2].valueAsText
        distance = int(parameters[3].valueAsText)
        bufferw = int(parameters[4].valueAsText)
        out_folder = parameters[5].valueAsText
        scratch_workspace = parameters[6].valueAsText

        with arcpy.EnvManager(scratchWorkspace=scratch_workspace):
            execute_create_zones(
                flowdir_raster,
                lakes,
                frompoint,
                distance,
                bufferw,
                out_folder,
                ArcGIStools,
                Messages(messages),
            )

        return
