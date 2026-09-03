import os

import arcpy

import ArcGIStools
from ArcGIS_Messages import Messages
from WidthByCrossSections import execute_WidthByCrossSections


class ArcGIS_WidthByCrossSections_Interface(object):
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
            direction="Input",
        )
        param_idfield = arcpy.Parameter(
            displayName="RouteID field",
            name="idfield",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
        )
        param_riverbed = arcpy.Parameter(
            displayName="River polygons",
            name="riverbed",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input",
        )
        param_ineffarea = arcpy.Parameter(
            displayName="Polygons identifying dead water",
            name="ineffarea",
            datatype="DEFeatureClass",
            parameterType="Optional",
            direction="Input",
        )
        param_maxwidth = arcpy.Parameter(
            displayName="Maximum width of cross-sections(m)",
            name="maxwidth",
            datatype="GPDouble",
            parameterType="Required",
            direction="Input",
        )
        param_spacing = arcpy.Parameter(
            displayName="Interval between cross-sections (m)",
            name="spacing",
            datatype="GPDouble",
            parameterType="Required",
            direction="Input",
        )
        param_transects = arcpy.Parameter(
            displayName="Output: Cross-sections",
            name="transects",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output",
        )
        param_cspoints = arcpy.Parameter(
            displayName="Output: Points at cross-section",
            name="outpts",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output",
        )

        project_path = arcpy.env.workspace
        if project_path not in [None, ""]:
            param_streamnetwork.value = os.path.join(project_path, "Geometry.gdb", "routes")
            param_riverbed.value = os.path.join(project_path, "Geometry.gdb", "channelpoly")
            param_transects.value = os.path.join(project_path, "Width.gdb", "width_transects")
            param_cspoints.value = os.path.join(project_path, "Width.gdb", "width_pts")
        param_idfield.parameterDependencies = [param_streamnetwork.name]
        param_idfield.value = "RID"
        param_maxwidth.value = 1000
        param_spacing.value = 5

        param_streamnetwork.filter.list = ["Polyline"]
        param_riverbed.filter.list = ["Polygon"]
        param_ineffarea.filter.list = ["Polygon"]

        return [
            param_streamnetwork,
            param_idfield,
            param_riverbed,
            param_ineffarea,
            param_maxwidth,
            param_spacing,
            param_transects,
            param_cspoints,
        ]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        del parameters
        return

    def updateMessages(self, parameters):
        parameters[7].clearMessage()
        if arcpy.Describe(arcpy.env.workspace).workspaceType != 'LocalDatabase':
            parameters[7].setErrorMessage('Tool needs a File Geodatabase as workspace to run properly.')
        del parameters
        return

    def execute(self, parameters, messages):
        execute_WidthByCrossSections(
            parameters[0].valueAsText,
            parameters[1].valueAsText,
            parameters[2].valueAsText,
            parameters[3].valueAsText,
            float(parameters[4].valueAsText),
            float(parameters[5].valueAsText),
            parameters[6].valueAsText,
            parameters[7].valueAsText,
            GIStools=ArcGIStools,
            messages=Messages(messages),
        )
        return


WidthByCrossSections = ArcGIS_WidthByCrossSections_Interface
