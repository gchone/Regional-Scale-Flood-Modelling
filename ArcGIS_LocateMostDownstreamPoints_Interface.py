import arcpy

from LocateMostDownstreamPoints import execute_LocateMostDownstreamPoints
import ArcGIStools
from ArcGIS_Messages import Messages


class LocateMostDownstreamPoints(object):
    def __init__(self):
        self.label = 'Locate most downstream points on network'
        self.description = 'Create an output point feature class with the most downstream points of a network.'
        self.canRunInBackground = True

    def getParameterInfo(self):
        param_network_shp = arcpy.Parameter(displayName='Network feature class', name='network_shp', datatype='GPFeatureLayer', parameterType='Required', direction='Input')
        param_links_table = arcpy.Parameter(displayName='Link table', name='links_table', datatype='GPTableView', parameterType='Required', direction='Input')
        param_RID_field = arcpy.Parameter(displayName='RouteID field in the network feature class', name='RID_field', datatype='Field', parameterType='Required', direction='Input')
        param_datapoints = arcpy.Parameter(displayName='Flow direction pixels along flow path table', name='datapoints', datatype='GPTableView', parameterType='Required', direction='Input')
        param_id_field_pts = arcpy.Parameter(displayName='ID field name from flow-path points table', name='id_field_pts', datatype='Field', parameterType='Required', direction='Input')
        param_RID_field_pts = arcpy.Parameter(displayName='RouteID field name from flow-path points table', name='RID_field_pts', datatype='Field', parameterType='Required', direction='Input')
        param_Distance_field_pts = arcpy.Parameter(displayName='Distance field name from flow-path points table', name='Distance_field_pts', datatype='Field', parameterType='Required', direction='Input')
        param_X_field_pts = arcpy.Parameter(displayName='X field name from flow-path points table', name='X_field_pts', datatype='Field', parameterType='Required', direction='Input')
        param_Y_field_pts = arcpy.Parameter(displayName='Y field name from flow-path points table', name='Y_field_pts', datatype='Field', parameterType='Required', direction='Input')
        param_output_pts = arcpy.Parameter(displayName='Output point feature class', name='output_pts', datatype='GPFeatureLayer', parameterType='Required', direction='Output')

        param_RID_field.parameterDependencies = [param_network_shp.name]
        param_id_field_pts.parameterDependencies = [param_datapoints.name]
        param_RID_field_pts.parameterDependencies = [param_datapoints.name]
        param_Distance_field_pts.parameterDependencies = [param_datapoints.name]
        param_X_field_pts.parameterDependencies = [param_datapoints.name]
        param_Y_field_pts.parameterDependencies = [param_datapoints.name]
        return [param_network_shp, param_links_table, param_RID_field, param_datapoints, param_id_field_pts, param_RID_field_pts, param_Distance_field_pts, param_X_field_pts, param_Y_field_pts, param_output_pts]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        execute_LocateMostDownstreamPoints(
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
            GIStools=ArcGIStools,
            messages=Messages(messages),
        )
        return
