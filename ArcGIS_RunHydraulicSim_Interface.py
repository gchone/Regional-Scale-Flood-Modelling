# -*- coding: utf-8 -*-

import os

import arcpy

from RunHydraulicSim import execute_RunHydraulicSim
import ArcGIStools
from ArcGIS_Messages import Messages


class Toolbox(object):
    def __init__(self):
        self.label = "Large Scale Flood Modeling Toolbox"
        self.alias = ""
        self.tools = [ArcGIS_RunHydraulicSim_Interface]


class ArcGIS_RunHydraulicSim_Interface(object):
    def __init__(self):
        self.label = "Run hydraulic simulations with LISFLOOD-FP"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        param_zones = arcpy.Parameter(
            displayName="Tiles folder",
            name="zones",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input",
        )
        param_inbci = arcpy.Parameter(
            displayName="Points with discharges (inbci.shp)",
            name="inbci",
            datatype="GPFeatureLayer",
            parameterType="Derived",
            direction="Input",
        )
        param_Qfields = arcpy.Parameter(
            displayName="Inbci fields with discharges",
            name="Qfields",
            datatype="Field",
            parameterType="Required",
            direction="Input",
            multiValue=True,
        )
        param_simfolder = arcpy.Parameter(
            displayName="Simulations folder",
            name="sim",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input",
        )
        param_lisflood = arcpy.Parameter(
            displayName="LISFLOOD-FP folder",
            name="lisflood",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input",
        )
        param_voutput = arcpy.Parameter(
            displayName="Ouput of flow velocity?",
            name="voutput",
            datatype="GPBoolean",
            parameterType="Required",
            direction="Input",
        )
        param_lakes = arcpy.Parameter(
            displayName="Downstream boundary polygons (lakes)",
            name="lakes",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input",
        )
        param_zfields = arcpy.Parameter(
            displayName="Field for boundary condition",
            name="z_field",
            datatype="Field",
            parameterType="Required",
            direction="Input",
            multiValue=True,
        )
        param_channelmanning = arcpy.Parameter(
            displayName="Channel Manning's n",
            name="channelmanning",
            datatype="GPDouble",
            parameterType="Required",
            direction="Input",
        )
        param_simtime = arcpy.Parameter(
            displayName="Maximum simulation time (s)",
            name="simtime",
            datatype="GPLong",
            parameterType="Required",
            direction="Input",
        )
        param_cfl = arcpy.Parameter(
            displayName="Courant–Friedrichs–Lewy condition",
            name="CFL",
            datatype="GPDouble",
            parameterType="Required",
            direction="Input",
        )
        param_zbed = arcpy.Parameter(
            displayName="D4 bed elevation raster",
            name="zbed",
            datatype="GPRasterLayer",
            parameterType="Required",
            direction="Input",
        )
        param_log = arcpy.Parameter(
            displayName="Log file",
            name="log",
            datatype="DEFile",
            parameterType="Required",
            direction="Output",
        )

        project_root = arcpy.env.workspace
        param_channelmanning.value = 0.03
        param_cfl.value = 0.5
        param_simtime.value = 300000
        param_voutput.value = False
        param_lakes.filter.list = ["Polygon"]
        param_zfields.parameterDependencies = [param_lakes.name]
        param_inbci.filter.list = ["Point"]
        param_Qfields.parameterDependencies = [param_inbci.name]

        param_zones.value = os.path.join(project_root, "Tiles")
        param_inbci.value = os.path.join(project_root, "Tiles", "inbci.shp")
        param_simfolder.value = os.path.join(project_root, "Sims")
        param_lakes.value = os.path.join(project_root, "Lisflood_inputs", "lakesforsim.shp")
        param_zbed.value = os.path.join(project_root, "Lisflood_inputs", "bathy_lisflood.tif")
        param_log.value = os.path.join(project_root, "Lisflood_inputs", "RunSim_log.txt")

        return [
            param_zones,
            param_inbci,
            param_Qfields,
            param_simfolder,
            param_lisflood,
            param_voutput,
            param_lakes,
            param_zfields,
            param_channelmanning,
            param_simtime,
            param_cfl,
            param_zbed,
            param_log,
        ]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        if parameters[0].valueAsText:
            parameters[1].value = parameters[0].valueAsText + "\\inbci.shp"
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        str_zones = parameters[0].valueAsText
        str_inbci = parameters[1].valueAsText
        list_qfields = _split_multivalue(parameters[2].valueAsText)
        messages.addMessage(list_qfields)
        str_simfolder = parameters[3].valueAsText
        str_lisflood = parameters[4].valueAsText
        voutput = parameters[5].valueAsText == "true"
        str_lakes = parameters[6].valueAsText
        list_zfields = _split_multivalue(parameters[7].valueAsText)
        channelmanning = float(parameters[8].valueAsText)
        simtime = int(parameters[9].valueAsText)
        cfl = float(parameters[10].valueAsText)
        zbed = arcpy.Raster(parameters[11].valueAsText)
        str_log = parameters[12].valueAsText

        if len(list_qfields) != len(list_zfields):
            messages.addErrorMessage("Number of downstream boundary condition should match the number of input discharges")
            return

        execute_RunHydraulicSim(
            tiles_folder=str_zones,
            simulations_folder=str_simfolder,
            lisflood_folder=str_lisflood,
            lakes=str_lakes,
            boundary_fields=list_zfields,
            output_velocity=voutput,
            simulation_time=simtime,
            cfl=cfl,
            channel_manning=channelmanning,
            zbed=zbed,
            discharge_fields=list_qfields,
            log_path=str_log,
            GIStools=ArcGIStools,
            messages=Messages(messages),
            inbci=str_inbci,
        )
        return


def _split_multivalue(value):
    if value in [None, ""]:
        return []
    return [item for item in value.split(";") if item not in [None, ""]]


RunSim_LISFLOOD = ArcGIS_RunHydraulicSim_Interface
