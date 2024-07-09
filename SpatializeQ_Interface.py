# -*- coding: utf-8 -*-


#####################################################
# Guénolé Choné
# Date:
# Description: Spatialize Q
#####################################################

from LargeScaleFloodMetaTools import *

class SpatializeQ(object):
    def __init__(self):
        self.label = "SpatializeQ Tool"
        self.description = ""
        self.canRunInBackground = True

    def getParameterInfo(self):
        param_route_D8 = arcpy.Parameter(
            displayName="Input route D8 feature class (lines)",
            name="route_D8",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_RID_field_D8 = arcpy.Parameter(
            displayName="RouteID field",
            name="RID_field_D8",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_D8pathpoints = arcpy.Parameter(
            displayName="D8 Pathpoints",
            name="D8pathpoints",
            datatype="GPTableView",
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
        param_routes = arcpy.Parameter(
            displayName="Input route feature class (lines)",
            name="routes",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_links = arcpy.Parameter(
            displayName="Routes links",
            name="links",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_RID_field = arcpy.Parameter(
            displayName="RID field in routes feature class",
            name="RID_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_Qorder_field = arcpy.Parameter(
            displayName="Ordering field in routes feature class",
            name="Qorder_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_Qpoints = arcpy.Parameter(
            displayName="Qpoints",
            name="Qpoints",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_id_field_Qpoints = arcpy.Parameter(
            displayName="Id field in Qpoints",
            name="id_field_Qpoints",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_RID_Qpoints = arcpy.Parameter(
            displayName="RID field in Qpoints",
            name="RID_Qpoints",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_dist_field_Qpoints = arcpy.Parameter(
            displayName="MEAS field in Qpoints ",
            name="dist_field_Qpoints",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_AtlasReach_field_Qpoints = arcpy.Parameter(
            displayName="AtlasReach field in Qpoints",
            name="AtlasReach_field_Qpoints",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_targetpoints = arcpy.Parameter(
            displayName="Target points",
            name="targetpoints",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_id_field_target = arcpy.Parameter(
            displayName="ID field in target points feature class",
            name="id_field_target",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_RID_field_target = arcpy.Parameter(
            displayName="RID field in target points feature class",
            name="RID_field_target",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_Distance_field_target = arcpy.Parameter(
            displayName="MEAS field in target points feature class",
            name="Distance_field_target",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_DEM_field_target = arcpy.Parameter(
            displayName="DEM field in target points feature class",
            name="DEM_field_target",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_Qcsv_file = arcpy.Parameter(
            displayName="Qcsv_file",
            name="Qcsv_file",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_output_points = arcpy.Parameter(
            displayName="Points Output table",
            name="output_points",
            datatype="GPTableView",
            parameterType="Required",
            direction="Output")

        param_RID_field_D8.parameterDependencies = [param_route_D8.name]
        param_RID_field.parameterDependencies = [param_routes.name]
        param_Qorder_field.parameterDependencies = [param_routes.name]
        param_id_field_Qpoints.parameterDependencies = [param_Qpoints.name]
        param_RID_Qpoints.parameterDependencies = [param_Qpoints.name]
        param_dist_field_Qpoints.parameterDependencies = [param_Qpoints.name]
        param_AtlasReach_field_Qpoints.parameterDependencies = [param_Qpoints.name]
        param_id_field_target.parameterDependencies = [param_targetpoints.name]
        param_RID_field_target.parameterDependencies = [param_targetpoints.name]
        param_Distance_field_target.parameterDependencies = [param_targetpoints.name]
        param_DEM_field_target.parameterDependencies = [param_targetpoints.name]

        params = [param_route_D8, param_RID_field_D8, param_D8pathpoints, param_relate_table, param_r_flowacc, param_routes, param_links, param_RID_field, param_Qorder_field, param_Qpoints, param_id_field_Qpoints, param_RID_Qpoints, param_dist_field_Qpoints, param_AtlasReach_field_Qpoints, param_targetpoints, param_id_field_target, param_RID_field_target, param_Distance_field_target, param_DEM_field_target, param_Qcsv_file, param_output_points]

        return params

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):

        route_D8 = parameters[0].valueAsText
        RID_field_D8 = parameters[1].valueAsText
        D8pathpoints = parameters[2].valueAsText
        relate_table = parameters[3].valueAsText
        r_flowacc = arcpy.Raster(parameters[4].valueAsText)
        routes = parameters[5].valueAsText
        links = parameters[6].valueAsText
        RID_field = parameters[7].valueAsText
        Qorder_field = parameters[8].valueAsText
        Qpoints = parameters[9].valueAsText
        id_field_Qpoints = parameters[10].valueAsText
        RID_Qpoints= parameters[11].valueAsText
        dist_field_Qpoints = parameters[12].valueAsText
        AtlasReach_field_Qpoints = parameters[13].valueAsText
        targetpoints = parameters[14].valueAsText
        id_field_target = parameters[15].valueAsText
        RID_field_target = parameters[16].valueAsText
        Distance_field_target = parameters[17].valueAsText
        DEM_field_target = parameters[18].valueAsText
        Qcsv_file = parameters[19].valueAsText
        output_points = parameters[20].valueAsText

        execute_SpatializeQ(route_D8, RID_field_D8, D8pathpoints, relate_table, r_flowacc, routes, links, RID_field, Qorder_field,
                            Qpoints, id_field_Qpoints, RID_Qpoints, dist_field_Qpoints,
                            AtlasReach_field_Qpoints, targetpoints, id_field_target,
                            RID_field_target, Distance_field_target, DEM_field_target, Qcsv_file, output_points, messages)

        return
