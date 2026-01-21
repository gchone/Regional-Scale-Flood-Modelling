# -*- coding: utf-8 -*-

#####################################################
# Guénolé Choné
# Concordia University
# Geography, Planning and Environment Department
# guenole.chone@concordia.ca
# Janvier 2019
#####################################################


import arcpy
from RunSim2DsupergcQlisted import *

class RunSim_LISFLOOD(object):
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
            direction="Input")
        param_inbci = arcpy.Parameter(
            displayName="Points with discharges (inbci.shp)",
            name="inbci",
            datatype="GPFeatureLayer",
            parameterType="Derived",
            direction="Input")
        param_Qfields = arcpy.Parameter(
            displayName="Inbci fields with discharges",
            name="Qfields",
            datatype="Field",
            parameterType="Required",
            direction="Input",
            multiValue = True)
        param_simfolder = arcpy.Parameter(
            displayName="Simulations folder",
            name="sim",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input")
        param_lisflood = arcpy.Parameter(
            displayName="LISFLOOD-FP folder",
            name="lisflood",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input")
        param_voutput = arcpy.Parameter(
            displayName="Ouput of flow velocity?",
            name="voutput",
            datatype="GPBoolean",
            parameterType="Required",
            direction="Input")
        param_lakes = arcpy.Parameter(
            displayName="Downstream boundary polygons (lakes)",
            name="lakes",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_zfields = arcpy.Parameter(
            displayName="Field for boundary condition",
            name="z_field",
            datatype="Field",
            parameterType="Required",
            direction="Input",
            multiValue = True)
        param_channelmanning = arcpy.Parameter(
            displayName="Channel Manning's n",
            name="channelmanning",
            datatype="GPDouble",
            parameterType="Required",
            direction="Input")
        param_simtime = arcpy.Parameter(
            displayName="Maximum simulation time (s)",
            name="simtime",
            datatype="GPLong",
            parameterType="Required",
            direction="Input")
        param_cfl = arcpy.Parameter(
            displayName="Courant–Friedrichs–Lewy condition",
            name="CFL",
            datatype="GPDouble",
            parameterType="Required",
            direction="Input")
        param_zbed = arcpy.Parameter(
            displayName="D4 bed elevation raster",
            name="zbed",
            datatype="GPRasterLayer",
            parameterType="Required",
            direction="Input")
        param_log = arcpy.Parameter(
            displayName="Log file",
            name="log",
            datatype="DEFile",
            parameterType="Required",
            direction="Output")


        param_channelmanning.value = 0.03
        param_cfl.value = 0.5
        param_simtime.value = 300000
        param_voutput.value = False
        param_lakes.filter.list = ["Polygon"]
        param_zfields.parameterDependencies = [param_lakes.name]
        param_inbci.filter.list = ["Point"]
        param_Qfields.parameterDependencies = [param_inbci.name]


        params = [param_zones, param_inbci, param_Qfields, param_simfolder, param_lisflood, param_voutput, param_lakes, param_zfields, param_channelmanning, param_simtime, param_cfl, param_zbed, param_log]

        return params

    def isLicensed(self):

        return True

    def updateParameters(self, parameters):
        if parameters[0].valueAsText:
            parameters[1].value = parameters[0].valueAsText + "\\inbci.shp"

        return

    def updateMessages(self, parameters):

        return

    def execute(self, parameters, messages):

        # Récupération des paramètres

        str_zones = parameters[0].valueAsText
        #inbci = parameters[1].valueAsText
        list_qfields = parameters[2].valueAsText.split(";")
        messages.addMessage(list_qfields)
        str_simfolder = parameters[3].valueAsText
        str_lisflood = parameters[4].valueAsText
        voutput = parameters[5].valueAsText == 'true'
        str_lakes = parameters[6].valueAsText
        list_zfields = parameters[7].valueAsText.split(";")
        channelmanning = float(parameters[8].valueAsText)
        simtime = int(parameters[9].valueAsText)
        cfl = float(parameters[10].valueAsText)
        zbed = arcpy.Raster(parameters[11].valueAsText)
        str_log = parameters[12].valueAsText
        if len(list_qfields) != len(list_zfields):
            messages.addErrorMessage("Number of downstream boundary condition should match the number of input discharges")
        else:
            execute_RunSim_prev(str_zones, str_simfolder, str_lisflood, str_lakes, list_zfields, voutput, simtime, cfl, channelmanning, zbed, list_qfields, str_log, messages)

        return

