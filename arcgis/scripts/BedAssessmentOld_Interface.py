# -*- coding: utf-8 -*-


from BedAssessmentLinearNet import *

class BedAssessmentIterations(object):
    def __init__(self):
        self.label = "Bed Assessment - Method by iterations"
        self.description = ""
        self.canRunInBackground = True

    def getParameterInfo(self):

        param_route = arcpy.Parameter(
            displayName="Route layer",
            name="route",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_route_RID_field = arcpy.Parameter(
            displayName="RouteID field",
            name="route_RID_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_route_order_field = arcpy.Parameter(
            displayName="Route Order field",
            name="route_order_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_routelinks = arcpy.Parameter(
            displayName="Route links",
            name="routelinks",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_points = arcpy.Parameter(
            displayName="Points",
            name="points",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")
        param_points_IDfield = arcpy.Parameter(
            displayName="Id field in datapoints",
            name="points_IDfield",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_points_RIDfield = arcpy.Parameter(
            displayName="RID field in datapoints",
            name="points_RIDfield",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_points_distfield = arcpy.Parameter(
            displayName="MEAS field in datapoints",
            name="points_distfield",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_points_Qfield = arcpy.Parameter(
            displayName="Q field",
            name="points_Qfield",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_points_Wfield = arcpy.Parameter(
            displayName="W field",
            name="points_Wfield",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_points_WSfield = arcpy.Parameter(
            displayName="WS field",
            name="points_WSfield",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_points_DEMfield = arcpy.Parameter(
            displayName="DEM field",
            name="points_DEMfield",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param_manning = arcpy.Parameter(
            displayName="Manning coefficient",
            name="manning",
            datatype="GPDouble",
            parameterType="Required",
            direction="Input")
        param_output_pts = arcpy.Parameter(
            displayName="Output table",
            name="output_pts",
            datatype="GPTableView",
            parameterType="Required",
            direction="Output")

        param_route_RID_field.parameterDependencies = [param_route.name]
        param_route_order_field.parameterDependencies = [param_route.name]
        param_points_IDfield.parameterDependencies = [param_points.name]
        param_points_RIDfield.parameterDependencies = [param_points.name]
        param_points_distfield.parameterDependencies = [param_points.name]
        param_points_Qfield.parameterDependencies = [param_points.name]
        param_points_Wfield.parameterDependencies = [param_points.name]
        param_points_WSfield.parameterDependencies = [param_points.name]
        param_points_DEMfield.parameterDependencies = [param_points.name]


        params = [param_route, param_route_RID_field, param_route_order_field, param_routelinks, param_points, param_points_IDfield, param_points_RIDfield, param_points_distfield, param_points_Qfield, param_points_Wfield, param_points_WSfield, param_points_DEMfield, param_manning, param_output_pts]

        return params

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        route = parameters[0].valueAsText
        route_RID_field = parameters[1].valueAsText
        route_order_field = parameters[2].valueAsText
        routelinks = parameters[3].valueAsText
        points = parameters[4].valueAsText
        points_IDfield= parameters[5].valueAsText
        points_RIDfield = parameters[6].valueAsText
        points_distfield = parameters[7].valueAsText
        points_Qfield = parameters[8].valueAsText
        points_Wfield = parameters[9].valueAsText
        points_WSfield = parameters[10].valueAsText
        points_DEMfield = parameters[11].valueAsText
        manning = float(parameters[12].valueAsText)
        output_pts = parameters[13].valueAsText

        execute_BedAssessment(route, route_RID_field, route_order_field, routelinks, points, points_IDfield, points_RIDfield, points_distfield, points_Qfield, points_Wfield, points_WSfield, points_DEMfield, manning, output_pts, messages)

        return
