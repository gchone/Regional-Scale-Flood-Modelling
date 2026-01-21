# -*- coding: utf-8 -*-

##################################################################
# Auteur: François Larouche-Tremblay, Ing, M Sc
# Description: Interface de la fonction LocaliserObstacles2D
##################################################################

# Versions:
# v1.0 - Sept 2019 - François Larouche-Tremblay - Creation
# v1.1 - May 2020 - Guénolé Choné - Brought into the FloodTools package.
# v1.2 - Mars 2023 - Guénolé Choné - English translation

import arcpy
from ChannelCorrection import *


class ChannelCorrection(object):
    def __init__(self):
        self.label = "Water surface correction"
        self.description = "Remove local bumps on water surface"
        self.canRunInBackground = True

    def getParameterInfo(self):
        param_mnt = arcpy.Parameter(
            displayName="DEM",
            name="mnt",
            datatype="GPRasterLayer",
            parameterType="Required",
            direction="Input")
        param_boundary = arcpy.Parameter(
            displayName="Downstream and upstream cross-sections",
            name="boundary",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_riverline = arcpy.Parameter(
            displayName="Rivers main channel lines",
            name="riverline",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_riverbed = arcpy.Parameter(
            displayName="River polygons",
            name="riverbed",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_footprints = arcpy.Parameter(
            displayName="DEM footprints",
            name="footprints",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_breachedmnt = arcpy.Parameter(
            displayName="Output: new DEM",
            name="breachedmnt",
            datatype="DERasterDataset",
            parameterType="Required",
            direction="Output")

        param_boundary.filter.list = ["Polyline"]
        param_riverbed.filter.list = ["Polygon"]
        param_footprints.filter.list = ["Polygon"]
        param_riverline.filter.list = ["Polyline"]

        params = [param_mnt, param_boundary, param_riverbed, param_riverline, param_footprints, param_breachedmnt]

        return params

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        # Récupération des paramètres
        mnt = arcpy.Raster(parameters[0].valueAsText)
        boundary = parameters[1].valueAsText
        riverbed = parameters[2].valueAsText
        riverline = parameters[3].valueAsText
        footprints = parameters[4].valueAsText
        breachedmnt = parameters[5].valueAsText

        execute_ChannelCorrection(mnt, boundary, riverbed, riverline, footprints, breachedmnt, messages)

        return
