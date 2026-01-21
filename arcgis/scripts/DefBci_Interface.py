# -*- coding: utf-8 -*-


#####################################################
# Guénolé Choné
# Concordia University
# Geography, Planning and Environment Department
# guenole.chone@concordia.ca
# Mars 2017
#####################################################

# v1.4 - Octobre 2019 - Input des débits à la limite de la tuile (v1.1, v1.2, v1.3) abandonné.
#       Retour à la v1.0 + Ajout du débit manquant lors d'une confluence + Valeurs par défaut + Ajout Minslope (au lieu de max) + Suppression param lacs
# v1.5 - Octobre 2019 - version modifiée pour simulations de l'amont vers l,aval avec reprise de l'élévation aval comme condition limite:
# v1.6 - Octobre 2019 - Débits ajustés jusqu'à la fin de la zone
# v1.7 - Mai 2020 - Séparation de l'interface


import os
import arcpy

from DefBciWithLateral_lakes_hdown import *


class DefBciWithLateralWlakes_hdown(object):
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
            direction="Input")
        param_flowacc = arcpy.Parameter(
            displayName="Flow accumulation",
            name="flowacc",
            datatype="GPRasterLayer",
            parameterType="Required",
            direction="Input")
        param_dist = arcpy.Parameter(
            displayName="Downstream boundary condition width (m)",
            name="distance",
            datatype="GPLong",
            parameterType="Required",
            direction="Input")
        param_percent = arcpy.Parameter(
            displayName="Drainage area variation for discharge correction (%)",
            name="percentdischarge",
            datatype="GPDouble",
            parameterType="Required",
            direction="Input")
        param_zones = arcpy.Parameter(
            displayName="Tiles folder",
            name="zones",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input")
        param_dem = arcpy.Parameter(
            displayName="DEM",
            name="dem",
            datatype="GPRasterLayer",
            parameterType="Required",
            direction="Input")
        param_width = arcpy.Parameter(
            displayName="D4 width",
            name="width",
            datatype="GPRasterLayer",
            parameterType="Required",
            direction="Input")
        param_zbed = arcpy.Parameter(
            displayName="D4 bed elevation",
            name="zbed",
            datatype="GPRasterLayer",
            parameterType="Required",
            direction="Input")
        param_manning = arcpy.Parameter(
            displayName="Floodplain Manning's n",
            name="manning",
            datatype="GPRasterLayer",
            parameterType="Required",
            direction="Input")
        param_mask = arcpy.Parameter(
            displayName="Channel mask",
            name="mask",
            datatype="GPRasterLayer",
            parameterType="Required",
            direction="Input")

        param_output = arcpy.Parameter(
            displayName="Output folder",
            name="folder",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input")
        param0 = arcpy.Parameter(
            displayName="Workspace",
            name="in_workspace",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input")

        param_dist.value = 4000
        param_percent.value = 1

        params = [param_flowdir, param_flowacc, param_dist, param_percent, param_zones, param_dem, param_width, param_zbed, param_manning, param_mask, param_output, param0]

        return params

    def isLicensed(self):

        return True

    def updateParameters(self, parameters):

        return

    def updateMessages(self, parameters):

        return

    def execute(self, parameters, messages):


        # Récupération des paramètres
        str_flowdir = parameters[0].valueAsText
        str_flowacc = parameters[1].valueAsText
        distoutput = int(parameters[2].valueAsText)
        percent = float(parameters[3].valueAsText)
        str_zonesfolder = parameters[4].valueAsText

        str_dem = parameters[5].valueAsText
        str_width = parameters[6].valueAsText
        str_zbed = parameters[7].valueAsText
        str_manning = parameters[8].valueAsText
        str_mask = parameters[9].valueAsText

        str_outputfolder = parameters[10].valueAsText

        arcpy.env.scratchWorkspace = parameters[11].valueAsText

        execute_DefBCI(arcpy.Raster(str_flowdir), arcpy.Raster(str_flowacc), distoutput, percent, str_zonesfolder,
                       arcpy.Raster(str_dem), arcpy.Raster(str_width), arcpy.Raster(str_zbed), arcpy.Raster(str_manning),
                       arcpy.Raster(str_mask), str_outputfolder, messages)


        return