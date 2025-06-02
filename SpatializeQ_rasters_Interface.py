# coding: latin-1

#####################################################
# Guénolé Choné
# Concordia University
# Geography, Planning and Environment Department
# guenole.chone@concordia.ca
#####################################################

# Versions
# v1.0 - May 2020 - Création.

import arcpy
from SpatializeQ_rasters import *


class SpatializeQ_rasters(object):
    def __init__(self):
        self.label = "D8 discharge spatialization"
        self.description = "Simple spatialization of discharges from points to raster using flow direction and flow accumulation rasters."
        self.canRunInBackground = True

    def getParameterInfo(self):

        param_flowdir = arcpy.Parameter(
            displayName="Flow direction",
            name="flowdir",
            datatype="GPRasterLayer",
            parameterType="Required",
            direction="Input")
        param_frompoint = arcpy.Parameter(
            displayName="Points de départ",
            name="frompoint",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_flowacc = arcpy.Parameter(
            displayName="Flow accumulation",
            name="flowacc",
            datatype="GPRasterLayer",
            parameterType="Required",
            direction="Input")
        param_q = arcpy.Parameter(
            displayName="Débits ponctuels",
            name="q",
            datatype="GPRasterLayer",
            parameterType="Required",
            direction="Input")
        param_interpolation = arcpy.Parameter(
            displayName="Interpolation entre les points de débits?",
            name="interpolation",
            datatype="GPBoolean",
            parameterType="Required",
            direction="Input")
        param_res = arcpy.Parameter(
            displayName="Output: lignes de débits (raster)",
            name="spatialq",
            datatype="DERasterDataset",
            parameterType="Required",
            direction="Output")

        param0 = arcpy.Parameter(
            displayName="Workspace",
            name="in_workspace",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input")

        param_interpolation.value = False
        params = [param_flowdir, param_frompoint, param_flowacc, param_q, param_interpolation, param_res, param0]

        return params

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        # Récupération des paramètres
        r_flowdir = arcpy.Raster(parameters[0].valueAsText)
        str_frompoint = parameters[1].valueAsText
        r_flowacc = arcpy.Raster(parameters[2].valueAsText)
        r_qpts = arcpy.Raster(parameters[3].valueAsText)
        interpolation = parameters[4].valueAsText == 'true'
        str_res = parameters[5].valueAsText
        arcpy.env.scratchWorkspace = parameters[6].valueAsText

        execute_SpatializeQ(r_flowdir, str_frompoint, r_flowacc, r_qpts, str_res, interpolation)

        return
