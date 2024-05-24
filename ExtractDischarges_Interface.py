# -*- coding: utf-8 -*-


#####################################################
# Guénolé Choné
# Date:
# Description: Extract Discharges
#####################################################

from LargeScaleFloodMetaTools import *

class ExtractDischarges(object):
    def __init__(self):
        self.label = "Extract Discharges Tool"
        self.description = ""
        self.canRunInBackground = True

    def getParameterInfo(self):
        param_routes_Atlas = arcpy.Parameter(
            displayName="Atlas route feature class (lines)",
            name="routes_Atlas",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_links_Atlas = arcpy.Parameter(
            displayName="Atlas route feature class links",
            name="links_Atlas",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_RID_field_Atlas = arcpy.Parameter(
            displayName="Atlas RouteID field",
            name="Rid_field_Atlas",
            datatype="FIeld",
            parameterType="Required",
            direction="Input")
        param_routes_AtlasD8 = arcpy.Parameter(
            displayName="Atlas D8 route feature class (lines)",
            name="routes_AtlasD8",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_links_AtlasD8 = arcpy.Parameter(
            displayName="Atlas D8 route feature class links",
            name="links_AtlasD8",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_RID_field_AtlasD8 = arcpy.Parameter(
            displayName="Atlas D8 RouteID field",
            name="RID_field_AtlasD8",
            datatype="FIeld",
            parameterType="Required",
            direction="Input")
        param_pts_D8 = arcpy.Parameter(
            displayName="Points D8",
            name="pts_D8",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_fpoints_atlas = arcpy.Parameter(
            displayName="From Points corresponding to Atlas",
            name="fpoints_atlas",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_routesD8 = arcpy.Parameter(
            displayName="Input route D8 feature class (lines)",
            name="routesD8",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_routeD8_RID = arcpy.Parameter(
            displayName="RouteID field in routeD8",
            name="routeD8_RID",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_routes_main = arcpy.Parameter(
            displayName="Input main route feature class (lines)",
            name="routes_main",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_route_main_RID = arcpy.Parameter(
            displayName="RouteID field in main route",
            name="route_main_RID",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_relate_table = arcpy.Parameter(
            displayName="Relate table",
            name="relate_table",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_r_flowacc = arcpy.Parameter(
            displayName="Flow Accumulation raster",
            name="r_flowacc",
            datatype="GPRasterLayer",
            parameterType="Required",
            direction="Input")
        param_outpoints_D8 = arcpy.Parameter(
            displayName="Points en D8 - Output points",
            name="outpoints",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output")
        param_outpoints_routes = arcpy.Parameter(
            displayName="Points on routes - Output points",
            name="outpoints2",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output")

        param_RID_field_Atlas.parameterDependencies = [param_routes_Atlas.name]
        param_RID_field_AtlasD8.parameterDependencies = [param_routes_AtlasD8.name]
        param_routeD8_RID.parameterDependencies = [param_routesD8.name]
        param_route_main_RID.parameterDependencies = [param_routes_main.name]

        params = [param_routes_Atlas, param_links_Atlas, param_RID_field_Atlas, param_routes_AtlasD8, param_links_AtlasD8, param_RID_field_AtlasD8, param_pts_D8, param_fpoints_atlas, param_routesD8, param_routeD8_RID, param_routes_main, param_route_main_RID, param_relate_table, param_r_flowacc, param_outpoints_D8, param_outpoints_routes]


        return params

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):

        routes_Atlas = parameters[0].valueAsText
        links_Atlas = parameters[1].valueAsText
        RID_field_Atlas = parameters[2].valueAsText
        routes_AtlasD8 = parameters[3].valueAsText
        links_AtlasD8 = parameters[4].valueAsText
        RID_field_AtlasD8 = parameters[5].valueAsText
        pts_D8 = parameters[6].valueAsText
        fpoints_atlas = parameters[7].valueAsText
        routesD8 = parameters[8].valueAsText
        routeD8_RID = parameters[9].valueAsText
        routes_main = parameters[10].valueAsText
        route_main_RID = parameters[11].valueAsText
        relate_table = parameters[12].valueAsText
        r_flowacc = arcpy.Raster(parameters[13].valueAsText)
        outpoints_D8 = parameters[14].valueAsText
        outpoints_routes = parameters[15].valueAsText

        execute_ExtractDischarges(routes_Atlas, links_Atlas, RID_field_Atlas, routes_AtlasD8, links_AtlasD8, RID_field_AtlasD8, pts_D8, fpoints_atlas, routesD8, routeD8_RID, routes_main, route_main_RID, relate_table, r_flowacc, outpoints_D8, outpoints_routes, messages)

        return
