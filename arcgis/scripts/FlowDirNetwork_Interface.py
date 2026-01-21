# -*- coding: utf-8 -*-


#####################################################
# Guénolé Choné
# Date:
# Description: Flow Direction Network
#####################################################

from LargeScaleFloodMetaTools import *

class FlowDirNetwork(object):
    def __init__(self):
        self.label = "Flow Direction Network"
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
        param_r_flow_dir= arcpy.Parameter(
            displayName="Flow Direction raster",
            name="r_flow_dir",
            datatype="GPRasterLayer",
            parameterType="Required",
            direction="Input")
        param_routeD8 = arcpy.Parameter(
            displayName="Output route D8 feature class (lines)",
            name="routeD8",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Output")
        param_linksD8 = arcpy.Parameter(
            displayName="Link table",
            name="linksD8",
            datatype="GPTableView",
            parameterType="Required",
            direction="Output")
        param_ptsonD8 = arcpy.Parameter(
            displayName="Point on route D8 feature class (lines)",
            name="ptsonD8",
            datatype="GPTableView",
            parameterType="Required",
            direction="Output")
        param_relatetable = arcpy.Parameter(
            displayName="Relate table",
            name="relatetable",
            datatype="GPTableView",
            parameterType="Required",
            direction="Output")


        param_RID_field.parameterDependencies = [param_routes.name]


        params = [param_routes, param_links, param_RID_field, param_r_flow_dir, param_routeD8, param_linksD8, param_ptsonD8, param_relatetable]


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
        r_flow_dir = arcpy.Raster(parameters[3].valueAsText)
        routeD8 = parameters[4].valueAsText
        linksD8 = parameters[5].valueAsText
        ptsonD8 = parameters[6].valueAsText
        relatetable = parameters[7].valueAsText


        execute_FlowDirNetwork(routes, links, RID_field, r_flow_dir, routeD8, linksD8, ptsonD8, relatetable, messages)
        return
