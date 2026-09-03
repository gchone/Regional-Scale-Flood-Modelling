# -*- coding: utf-8 -*-

import os

import arcpy

from HydraulicSimPrep import prepare_hydraulic_sim
import ArcGIStools
from ArcGIS_Messages import Messages


class Toolbox(object):
    def __init__(self):
        self.label = "Large Scale Flood Modeling Toolbox"
        self.alias = ""
        self.tools = [ArcGIS_HydraulicSimPrep_Interface]


class ArcGIS_HydraulicSimPrep_Interface(object):
    def __init__(self):
        self.label = "Hydraulic simulations preparation"
        self.description = "Create input files for LISFLOOD-FP for each tile"
        self.canRunInBackground = False

    def getParameterInfo(self):
        param_flowdir = arcpy.Parameter(
            displayName="Flow direction",
            name="flowdir",
            datatype="GPRasterLayer",
            parameterType="Required",
            direction="Input",
        )
        param_flowacc = arcpy.Parameter(
            displayName="Flow accumulation",
            name="flowacc",
            datatype="GPRasterLayer",
            parameterType="Required",
            direction="Input",
        )
        param_percent = arcpy.Parameter(
            displayName="Drainage area variation for discharge correction (%)",
            name="percentdischarge",
            datatype="GPDouble",
            parameterType="Required",
            direction="Input",
        )
        param_zones = arcpy.Parameter(
            displayName="Tiles folder",
            name="zones",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input",
        )
        param_dem = arcpy.Parameter(
            displayName="DEM",
            name="dem",
            datatype="GPRasterLayer",
            parameterType="Required",
            direction="Input",
        )
        param_width = arcpy.Parameter(
            displayName="D4 width",
            name="width",
            datatype="GPRasterLayer",
            parameterType="Required",
            direction="Input",
        )
        param_zbed = arcpy.Parameter(
            displayName="D4 bed elevation",
            name="zbed",
            datatype="GPRasterLayer",
            parameterType="Required",
            direction="Input",
        )
        param_manning = arcpy.Parameter(
            displayName="Floodplain Manning's n",
            name="manning",
            datatype="GPRasterLayer",
            parameterType="Required",
            direction="Input",
        )
        param_mask = arcpy.Parameter(
            displayName="Channel mask",
            name="mask",
            datatype="GPRasterLayer",
            parameterType="Required",
            direction="Input",
        )
        param_output = arcpy.Parameter(
            displayName="Output folder",
            name="folder",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input",
        )
        param_workspace = arcpy.Parameter(
            displayName="Workspace",
            name="in_workspace",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input",
        )

        param_percent.value = 1
        param_workspace.filter.list = ["File System"]

        project_root = arcpy.env.workspace
        if project_root not in [None, ""]:
            param_flowdir.value = os.path.join(project_root, "10mDEMs.gdb", "lidar10m_fd")
            param_flowacc.value = os.path.join(project_root, "10mDEMs.gdb", "lidar10m_facc")
            param_zones.value = os.path.join(project_root, "Tiles")
            param_dem.value = os.path.join(project_root, "10mDEMs.gdb", "lidar10m_avg")
            param_width.value = os.path.join(project_root, "Lisflood_inputs", "width_lisflood.tif")
            param_zbed.value = os.path.join(project_root, "Lisflood_inputs", "bathy_lisflood.tif")
            param_manning.value = os.path.join(project_root, "Lisflood_inputs", "n_floodplain.tif")
            param_mask.value = os.path.join(project_root, "Lisflood_inputs", "mask.tif")
            param_output.value = os.path.join(project_root, "Sims")
            param_workspace.value = os.path.join(project_root, "temp")

        return [
            param_flowdir,
            param_flowacc,
            param_percent,
            param_zones,
            param_dem,
            param_width,
            param_zbed,
            param_manning,
            param_mask,
            param_output,
            param_workspace,
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
        percent = float(parameters[2].valueAsText)
        with arcpy.EnvManager(scratchWorkspace=parameters[10].valueAsText):
            prepare_hydraulic_sim(
                flowdir_raster=arcpy.Raster(parameters[0].valueAsText),
                flowacc_raster=arcpy.Raster(parameters[1].valueAsText),
                percent=percent,
                zones_folder=parameters[3].valueAsText,
                dem_raster=arcpy.Raster(parameters[4].valueAsText),
                width_raster=arcpy.Raster(parameters[5].valueAsText),
                zbed_raster=arcpy.Raster(parameters[6].valueAsText),
                manning_raster=arcpy.Raster(parameters[7].valueAsText),
                mask_raster=arcpy.Raster(parameters[8].valueAsText),
                output_folder=parameters[9].valueAsText,
                GIStools=ArcGIStools,
                messages=Messages(messages),
            )
        return


DefBciWithLateralWlakes_hdown = ArcGIS_HydraulicSimPrep_Interface
