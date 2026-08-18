# -*- coding: utf-8 -*-

#####################################################
# Auteur: François Larouche-Tremblay, Ing, M Sc
# Date: 04/05/2021
# Description: Interface de la fonction LargeurParTransect
#
# 03/24/2023: English interface - Guénolé Choné
#####################################################

import arcpy
from WidthAssessment import *
import os

class LargeurParTransect(object):
    def __init__(self):
        self.label = "Width by cross-sections"
        self.description = ""
        self.canRunInBackground = True

    def getParameterInfo(self):
        param_streamnetwork = arcpy.Parameter(
            displayName="Route layer (or lines)",
            name="streamnetwork",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input")
        param_idfield = arcpy.Parameter(
            displayName="RouteID field",
            name="idfield",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        param_riverbed = arcpy.Parameter(
            displayName="River polygons",
            name="riverbed",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input")
        param_ineffarea = arcpy.Parameter(
            displayName="Polygons identifying dead water",
            name="ineffarea",
            datatype="DEFeatureClass",
            parameterType="Optional",
            direction="Input")
        param_maxwidth = arcpy.Parameter(
            displayName="Maximum width of cross-sections(m)",
            name="maxwidth",
            datatype="GPDouble",
            parameterType="Required",
            direction="Input")
        param_spacing = arcpy.Parameter(
            displayName="Interval between cross-sections (m)",
            name="spacing",
            datatype="GPDouble",
            parameterType="Required",
            direction="Input")
        param_transects = arcpy.Parameter(
            displayName="Output: Cross-sections",
            name="transects",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output")
        param_cspoints = arcpy.Parameter(
            displayName="Output: Points at cross-section",
            name="outpts",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output")

        # Set default values similar to ExtractWaterSurface_Interface

        project_path = arcpy.env.workspace
        param_streamnetwork.value = os.path.join(project_path, "Geometry.gdb", "routes")
        param_idfield.parameterDependencies = [param_streamnetwork.name]
        param_idfield.value = "RID"
        param_riverbed.value = os.path.join(project_path, "Geometry.gdb", "channelpoly")

        param_maxwidth.value = 1000
        param_spacing.value = 5
        param_transects.value = os.path.join(project_path, "Width.gdb", "width_transects")
        param_cspoints.value = os.path.join(project_path, "Width.gdb", "width_pts")

        param_streamnetwork.filter.list = ["Polyline"]
        param_riverbed.filter.list = ["Polygon"]
        param_ineffarea.filter.list = ["Polygon"]

        params = [param_streamnetwork, param_idfield, param_riverbed, param_ineffarea, param_maxwidth,
                  param_spacing, param_transects, param_cspoints]

        return params

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        parameters[7].clearMessage()
        if arcpy.Describe(arcpy.env.workspace) != 'FileGDB':
            parameters[7].setErrorMessage('Tool needs a File Geodatabase as workspace to run properly.')
        return

    def execute(self, parameters, messages):
        # Récupération des paramètres

        streamnetwork = parameters[0].valueAsText
        idfield = parameters[1].valueAsText
        riverbed = parameters[2].valueAsText
        ineffarea = parameters[3].valueAsText
        maxwidth = int(parameters[4].valueAsText)
        spacing = float(parameters[5].valueAsText)
        transects = parameters[6].valueAsText
        cspoints = parameters[7].valueAsText

        execute_largeurpartransect(streamnetwork, idfield, riverbed, ineffarea, maxwidth, spacing,
                                   transects, cspoints, messages)

        return
