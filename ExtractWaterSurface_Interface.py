# -*- coding: utf-8 -*-


#####################################################
# Guénolé Choné
# Date:
# Description: Extract Water Surface
#####################################################

from LargeScaleFloodMetaTools import *

class ExtractWaterSurface(object):
    def __init__(self):
        self.label = "Extract Water Surface"
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
            displayName="Input route link table",
            name="links",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_RID_field = arcpy.Parameter(
            displayName="RouteID field in the Input route feature class",
            name="RID_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_order_field = arcpy.Parameter(
            displayName="Order field in the Input route feature class (from 'Order reaches tool')",
            name="order_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_routes_3m = arcpy.Parameter(
            displayName="Input route 3m feature class (lines)",
            name="routes_3m",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_RID_field_3m = arcpy.Parameter(
            displayName="RouteID field in route 3m feature class",
            name="RID_field_3m",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_relate_table = arcpy.Parameter(
            displayName="Relate table",
            name="relate_table",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_pts_table = arcpy.Parameter(
            displayName="Points table",
            name="pts_table",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_X_field_pts = arcpy.Parameter(
            displayName="Name of X field",
            name="X_field_pts",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_Y_field_pts = arcpy.Parameter(
            displayName="Name of Y field",
            name="Y_field_pts",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_lidar3m_cor = arcpy.Parameter(
            displayName="Lidar 3m cor",
            name="lidar3m_cor",
            datatype="GPRasterLayer",
            parameterType="Required",
            direction="Input")
        param_DEMs_footprints = arcpy.Parameter(
            displayName="DEMs footprint feature class",
            name="DEMs_footprints",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_DEMs_field = arcpy.Parameter(
            displayName="DEMs field in DEMs footprint feature class",
            name="DEMs_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_targets = arcpy.Parameter(
            displayName="Target points to extract water surface",
            name="targets",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_targets_id_field = arcpy.Parameter(
            displayName="ID field in the target points table",
            name="targets_id_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_targets_rid_field = arcpy.Parameter(
            displayName="Route ID field in the target points table",
            name="targets_rid_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_targets_distfield = arcpy.Parameter(
            displayName="Distance field in the target points on network layer",
            name="targets_distfield",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_output_table = arcpy.Parameter(
            displayName="Output Points table",
            name="output_table",
            datatype="GPTableView",
            parameterType="Required",
            direction="Output")

        param_RID_field.parameterDependencies = [param_routes.name]
        param_order_field.parameterDependencies = [param_routes.name]
        param_RID_field_3m.parameterDependencies = [param_routes_3m.name]
        param_X_field_pts.parameterDependencies = [param_pts_table.name]
        param_Y_field_pts.parameterDependencies = [param_pts_table.name]
        param_DEMs_field.parameterDependencies = [param_DEMs_footprints.name]
        param_targets_id_field.parameterDependencies = [param_targets.name]
        param_targets_rid_field.parameterDependencies = [param_targets.name]
        param_targets_distfield.parameterDependencies = [param_targets.name]

        params = [param_routes, param_links, param_RID_field, param_order_field, param_routes_3m, param_RID_field_3m, param_relate_table, param_pts_table, param_X_field_pts, param_Y_field_pts, param_lidar3m_cor, param_DEMs_footprints, param_DEMs_field, param_targets, param_targets_id_field, param_targets_rid_field, param_targets_distfield, param_output_table]


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
        order_field = parameters[3].valueAsText
        routes_3m = parameters[4].valueAsText
        RID_field_3m = parameters[5].valueAsText
        relate_table = parameters[6].valueAsText
        pts_table = parameters[7].valueAsText
        X_field_pts = parameters[8].valueAsText
        Y_field_pts = parameters[9].valueAsText
        lidar3m_cor = arcpy.Raster(parameters[10].valueAsText)
        DEMs_footprints = parameters[11].valueAsText
        DEMs_field = parameters[12].valueAsText
        targetpoints = parameters[13].valueAsText
        id_field_target = parameters[14].valueAsText
        RID_field_target = parameters[15].valueAsText
        Distance_field_target = parameters[16].valueAsText
        ouput_table = parameters[17].valueAsText


        execute_ExtractWaterSurface(routes, links, RID_field, order_field, routes_3m, RID_field_3m, relate_table, pts_table, X_field_pts,
                                    Y_field_pts, lidar3m_cor, DEMs_footprints,
                                    DEMs_field, targetpoints, id_field_target, RID_field_target, Distance_field_target, ouput_table, messages)
        return
