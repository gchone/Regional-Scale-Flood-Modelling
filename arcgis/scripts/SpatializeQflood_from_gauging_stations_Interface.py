# -*- coding: utf-8 -*-


#####################################################
# Guénolé Choné
# Date:
# Description: Spatialize Q floods
#####################################################

from LargeScaleFloodMetaTools import *

class SpatializeQflood_gauging_stations(object):
    def __init__(self):
        self.label = "Spatialize discharges from gauging stations - Flood discharge"
        self.description = ""
        self.canRunInBackground = True

    def getParameterInfo(self):

        param_r_flowacc = arcpy.Parameter(
            displayName="Flow Accumulation raster",
            name="r_flowacc",
            datatype="GPRasterLayer",
            parameterType="Required",
            direction="Input")
        param_routes = arcpy.Parameter(
            displayName="Input D8 route feature class",
            name="routes",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_RID_field = arcpy.Parameter(
            displayName="RID field in routes feature class",
            name="RID_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_links = arcpy.Parameter(
            displayName="Routes D8 links",
            name="links",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_ptsonD8 = arcpy.Parameter(
            displayName="Point on route D8 feature class (lines)",
            name="ptsonD8",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_Qpoints = arcpy.Parameter(
            displayName="Qpoints",
            name="Qpoints",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_id_field_Qpoints = arcpy.Parameter(
            displayName="Id field in Qpoints",
            name="id_field_Qpoints",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_name_Qpoints = arcpy.Parameter(
            displayName="Gauging station name in Qpoints",
            name="name_Qpoints",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_drainage_Qpoints = arcpy.Parameter(
            displayName="Drainage area in Qpoints",
            name="drainage_Qpoints",
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
        param_Q_field_Qpoints = arcpy.Parameter(
            displayName="Discharge field in Qpoints ",
            name="Q_field_Qpoints",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_beta = arcpy.Parameter(
            displayName="Beta coefficient",
            name="Beta",
            datatype="GPDouble",
            parameterType="Required",
            direction="Input")
        param_output_points = arcpy.Parameter(
            displayName="Points Output table",
            name="output_points",
            datatype="GPTableView",
            parameterType="Required",
            direction="Output")


        param_RID_field.parameterDependencies = [param_routes.name]
        param_id_field_Qpoints.parameterDependencies = [param_Qpoints.name]
        param_RID_Qpoints.parameterDependencies = [param_Qpoints.name]
        param_name_Qpoints.parameterDependencies = [param_Qpoints.name]
        param_drainage_Qpoints.parameterDependencies = [param_Qpoints.name]
        param_dist_field_Qpoints.parameterDependencies = [param_Qpoints.name]
        param_Q_field_Qpoints.parameterDependencies = [param_Qpoints.name]



        params = [param_r_flowacc, param_routes, param_RID_field, param_links, param_ptsonD8, param_Qpoints,
                  param_id_field_Qpoints, param_name_Qpoints, param_drainage_Qpoints, param_RID_Qpoints,
                  param_dist_field_Qpoints, param_Q_field_Qpoints, param_beta, param_output_points]

        return params

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):

        r_flowacc = arcpy.Raster(parameters[0].valueAsText)
        routes = parameters[1].valueAsText
        RID_field = parameters[2].valueAsText
        links = parameters[3].valueAsText
        D8pathpoints = parameters[4].valueAsText
        Qpoints = parameters[5].valueAsText
        id_field_Qpoints = parameters[6].valueAsText
        name_Qpoints = parameters[7].valueAsText
        drainage_Qpoints = parameters[8].valueAsText
        RID_Qpoints= parameters[9].valueAsText
        dist_field_Qpoints = parameters[10].valueAsText
        Q_field_Qpoints = parameters[11].valueAsText
        beta_coef = float(parameters[12].valueAsText)
        output_points = parameters[13].valueAsText

        execute_SpatializeQ_from_gauging_stations(routes, links, RID_field, D8pathpoints, r_flowacc, Qpoints,
                                                  id_field_Qpoints, name_Qpoints, drainage_Qpoints, RID_Qpoints, dist_field_Qpoints, Q_field_Qpoints, None, None,
                                                  None, beta_coef, output_points, messages)

        return
