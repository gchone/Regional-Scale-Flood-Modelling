# -*- coding: utf-8 -*-


#####################################################
# Guénolé Choné
# Date:
# Description: Order Reaches
#####################################################

from LargeScaleFloodMetaTools import *

class OrderReaches(object):
    def __init__(self):
        self.label = "Order reaches"
        self.description = ""
        self.canRunInBackground = True

    def getParameterInfo(self):
        param_routes = arcpy.Parameter(
            displayName="Input route feature class (lines)",
            name="routes",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_links = arcpy.Parameter(
            displayName="Link table",
            name="links",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_RID_field = arcpy.Parameter(
            displayName="RouteID field",
            name="RID_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_r_flowacc= arcpy.Parameter(
            displayName="Flow accumulation raster",
            name="r_flowacc",
            datatype="GPRasterLayer",
            parameterType="Required",
            direction="Input")
        param_routeD8 = arcpy.Parameter(
            displayName="Input route D8 feature class (lines)",
            name="routeD8",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_linksD8 = arcpy.Parameter(
            displayName="Link table",
            name="linksD8",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_ptsonD8 = arcpy.Parameter(
            displayName="Point on route D8 feature class (lines)",
            name="ptsonD8",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_relatetable = arcpy.Parameter(
            displayName="Relate table",
            name="relatetable",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_outputfield = arcpy.Parameter(
            displayName="Output field",
            name="outputfield",
            datatype="GPString",
            parameterType="Required",
            direction="Input")

        param_RID_field.parameterDependencies = [param_routes.name]


        params = [param_routes, param_links, param_RID_field, param_r_flowacc, param_routeD8, param_linksD8, param_ptsonD8, param_relatetable, param_outputfield]


        return params

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):

        routes = parameters[0].valueAsText
        links = parameters[1].valueAsText
        RID_field = parameters[2].valueAsText
        r_flowacc = parameters[3].valueAsText
        routeD8 = parameters[4].valueAsText
        linksD8 = parameters[5].valueAsText
        ptsonD8 = parameters[6].valueAsText
        relatetable = parameters[7].valueAsText
        outputfield = parameters[8].valueAsText

        execute_OrderReaches(routes, links, RID_field, r_flowacc, routeD8, linksD8, ptsonD8, relatetable, outputfield, messages)
        return
