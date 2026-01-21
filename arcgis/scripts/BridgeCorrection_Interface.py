# coding: latin-1

#####################################################
# Guénolé Choné
# Concordia University
# Geography, Planning and Environment Department
# guenole.chone@concordia.ca
#####################################################

# Versions
# v1.0 - Juillet 2018 - Création
# v1.1 - Décembre 2018 - English version
# v1.2 - Mai 2020 - Externalisation du code metier

import arcpy
from BridgeCorrection import *

class BridgeCorrection(object):
    def __init__(self):

        self.label = "Bridges and culverts correction"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):

        param_raster = arcpy.Parameter(
            displayName="DEM",
            name="raster",
            datatype="GPRasterLayer",
            parameterType="Required",
            direction="Input")
        param_bridges = arcpy.Parameter(
            displayName="Bridges to be corrected",
            name="bridges",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_res = arcpy.Parameter(
            displayName="Result - Corrected DEM",
            name="result",
            datatype="DERasterDataset",
            parameterType="Required",
            direction="Output")

        param_bridges.filter.list = ["Polygon"]

        params = [param_raster, param_bridges, param_res]

        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        return

    def execute(self, parameters, messages):
        """The source code of the tool."""

        # Récupération des paramètres
        str_raster = parameters[0].valueAsText
        polygons = parameters[1].valueAsText
        SaveResult = parameters[2].valueAsText

        execute_BridgeCorrection(arcpy.Raster(str_raster), polygons, SaveResult, messages, language="EN")


        return