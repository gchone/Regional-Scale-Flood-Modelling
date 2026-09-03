# coding: latin-1

import arcpy

from WSsmoothing import *
import ArcGIStools
from ArcGIS_Messages import Messages


class Toolbox(object):
    def __init__(self):
        self.label = "Large Scale Flood Modeling Toolbox"
        self.alias = ""
        self.tools = [ArcGIS_WSsmoothing_Interface]


class ArcGIS_WSsmoothing_Interface(object):
    def __init__(self):
        self.label = "Denoise and smooth water surface"
        self.description = ""
        self.canRunInBackground = True

    def getParameterInfo(self):
        param_routes = arcpy.Parameter(
            displayName="Input route feature class (lines)",
            name="routes",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input",
        )
        param_links = arcpy.Parameter(
            displayName="Input route link table",
            name="links",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input",
        )
        param_RID_field = arcpy.Parameter(
            displayName="RouteID field in the Input route feature class",
            name="RID_field",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_order_field = arcpy.Parameter(
            displayName="Order field in the Input route feature class (from 'Order reaches tool')",
            name="order_field",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_points = arcpy.Parameter(
            displayName="Points with water surface information",
            name="points",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input",
        )
        param_pts_id_field = arcpy.Parameter(
            displayName="ID field in the points table",
            name="pts_id_field",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_pts_rid_field = arcpy.Parameter(
            displayName="Route ID field in the points table",
            name="pts_rid_field",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_pts_distfield = arcpy.Parameter(
            displayName="Distance field in the points table",
            name="pts_distfield",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_pts_wsfield = arcpy.Parameter(
            displayName="Water surface elevation field in the points table",
            name="pts_wsfield",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_pts_demfield = arcpy.Parameter(
            displayName="DEM field in the points table",
            name="pts_demfield",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_quantile = arcpy.Parameter(
            displayName="Quantile for carving",
            name="quantile",
            datatype="GPDouble",
            parameterType="Required",
            direction="Input",
        )
        param_smoothing = arcpy.Parameter(
            displayName="Apply smoothing?",
            name="smoothing",
            datatype="GPBoolean",
            parameterType="Required",
            direction="Input",
        )
        param_smooth_level = arcpy.Parameter(
            displayName="Global smoothing level (standard deviation)",
            name="smooth_level",
            datatype="GPDouble",
            parameterType="Required",
            direction="Input",
        )
        param_uncertainty_sigma = arcpy.Parameter(
            displayName="Standard deviation for uncertainty measurement",
            name="uncertainty_sigma",
            datatype="GPDouble",
            parameterType="Required",
            direction="Input",
        )
        param_uncertainty_factor = arcpy.Parameter(
            displayName="Effect of uncertainty on the smoothing (0 = no effect)",
            name="uncertainty_factor",
            datatype="GPDouble",
            parameterType="Required",
            direction="Input",
        )
        param_slope_sigma = arcpy.Parameter(
            displayName="Standard deviation for slope measurement",
            name="slope_sigma",
            datatype="GPDouble",
            parameterType="Required",
            direction="Input",
        )
        param_slope_factor = arcpy.Parameter(
            displayName="Effect of slope on the smoothing (0 = no effect)",
            name="slope_factor",
            datatype="GPDouble",
            parameterType="Required",
            direction="Input",
        )
        param_rdp = arcpy.Parameter(
            displayName="Water surface simplification by the Ramer-Douglas-Peucker algorithm",
            name="rdp_value",
            datatype="GPDouble",
            parameterType="Optional",
            direction="Input",
        )
        param_output_table = arcpy.Parameter(
            displayName="Output Points table",
            name="output_table",
            datatype="GPTableView",
            parameterType="Required",
            direction="Output",
        )

        param_RID_field.parameterDependencies = [param_routes.name]
        param_order_field.parameterDependencies = [param_routes.name]
        param_pts_id_field.parameterDependencies = [param_points.name]
        param_pts_rid_field.parameterDependencies = [param_points.name]
        param_pts_distfield.parameterDependencies = [param_points.name]
        param_pts_wsfield.parameterDependencies = [param_points.name]
        param_pts_demfield.parameterDependencies = [param_points.name]
        param_quantile.value = 0.2
        param_smoothing.value = True
        param_smooth_level.value = 600
        param_uncertainty_sigma.value = 300
        param_uncertainty_factor.value = 0.85
        param_slope_sigma.value = 300
        param_slope_factor.value = 2.0
        param_rdp.value = 0.02

        return [
            param_routes,
            param_links,
            param_RID_field,
            param_order_field,
            param_points,
            param_pts_id_field,
            param_pts_rid_field,
            param_pts_distfield,
            param_pts_wsfield,
            param_pts_demfield,
            param_quantile,
            param_smoothing,
            param_smooth_level,
            param_uncertainty_sigma,
            param_uncertainty_factor,
            param_slope_sigma,
            param_slope_factor,
            param_rdp,
            param_output_table,
        ]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        if parameters[11].valueAsText == "true":
            parameters[12].enabled = True
            parameters[13].enabled = True
            parameters[14].enabled = True
            parameters[15].enabled = True
            parameters[16].enabled = True
        else:
            parameters[12].enabled = False
            parameters[13].enabled = False
            parameters[14].enabled = False
            parameters[15].enabled = False
            parameters[16].enabled = False
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        execute_WSprocessing(
            parameters[0].valueAsText,
            parameters[1].valueAsText,
            parameters[2].valueAsText,
            parameters[3].valueAsText,
            parameters[4].valueAsText,
            parameters[5].valueAsText,
            parameters[6].valueAsText,
            parameters[7].valueAsText,
            parameters[8].valueAsText,
            parameters[9].valueAsText,
            parameters[18].valueAsText,
            ArcGIStools,
            Messages(messages),
            quantile=float(parameters[10].valueAsText),
            smooth_level=float(parameters[12].valueAsText),
            uncertainty_sigma=float(parameters[13].valueAsText),
            uncertainty_factor=float(parameters[14].valueAsText),
            slope_sigma=float(parameters[15].valueAsText),
            slope_factor=float(parameters[16].valueAsText),
            smoothing=parameters[11].valueAsText == "true",
            rdp_epsilon=float(parameters[17].valueAsText) if parameters[17].valueAsText else None,
        )
        return
