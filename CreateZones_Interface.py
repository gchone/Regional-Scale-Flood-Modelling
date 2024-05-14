# coding: latin-1

#####################################################
# Guénolé Choné
# Concordia University
# Geography, Planning and Environment Department
# guenole.chone@concordia.ca
# Fevrier 2019
#####################################################

# v1.1 - 10 mai 2018 - Correction des problèmes de zones dupliquées aux confluences (due aux segments d'un pixel de
#   long). Correction des longueurs des segments aux confluences.
# v1.2 - 28 février 2019 - Suppression des coupures aux confluences, ajout des coupures aux lacs.
# v1.3 - septembre 2019 - Coupure nette des rasters aux lacs + ajout du critère de pente
# v1.4 - octobre 2019 - Debug : problème de coupure des lacs avec multi fp, problème si zone de lac trop courte
# v1.5 - fevrier 2020 - Debug : problème de clip pour les confluent des segments coupé par les lacs
# v1.6 - mai 2020 - Coupure pour SUB et SUPER GC - Séparation interface et metier

import arcpy
from CreateZonesWlakesWSlope import *

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
        param0 = arcpy.Parameter(
            displayName="Workspace",
            name="in_workspace",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input")

        param0.filter.list = ["File System"]
        param0.value = arcpy.env.scratchWorkspace
        param_frompoint.filter.list = ["Point"]
        param_lakes.filter.list = ["POLYGON"]
        param_distance.value = 15000
        param_bufferw.value = 3000

        params = [param_flowdir, param_lakes, param_frompoint, param_distance, param_bufferw, param_folder, param0]

        return params

    def isLicensed(self):

        return True

    def updateParameters(self, parameters):
        # # For the version with a slope criteria
        # if parameters[2].valueAsText and parameters[2].valueAsText != "#":
        #     parameters[3].enabled = True
        #     parameters[3].value = 0.001
        # else:
        #     parameters[3].enabled = False
        return

    def updateMessages(self, parameters):

        return

    def execute(self, parameters, messages):


        # Récupération des paramètres
        r_flowdir = arcpy.Raster(parameters[0].valueAsText)
        str_lakes = parameters[1].valueAsText
        r_slope = None
        minslope = None
        str_frompoint = parameters[2].valueAsText
        distance = int(parameters[3].valueAsText)
        bufferw = int(parameters[4].valueAsText)
        str_folder = parameters[5].valueAsText

        arcpy.env.scratchWorkspace = parameters[6].valueAsText

        execute_CreateZone(r_flowdir, str_lakes, r_slope, minslope, str_frompoint, distance, bufferw, str_folder, messages)

        return





