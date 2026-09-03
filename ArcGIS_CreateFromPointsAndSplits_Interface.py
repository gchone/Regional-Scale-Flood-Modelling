import os
import arcpy

from CreateFromPointsAndSplits import execute_CreateFromPointsAndSplits
import ArcGIStools
from ArcGIS_Messages import Messages


class CreateFromPointsAndSplits(object):
    def __init__(self):
        self.label = 'Create from points and split points'
        self.description = 'Create from points and split points along a network.'
        self.canRunInBackground = True

    def getParameterInfo(self):
        param_network_shp = arcpy.Parameter(displayName='Network feature class', name='network_shp', datatype='DEFeatureClass', parameterType='Required', direction='Input')
        param_links_table = arcpy.Parameter(displayName='Link table', name='links_table', datatype='GPTableView', parameterType='Required', direction='Input')
        param_RID_field = arcpy.Parameter(displayName='RouteID field in the network feature class', name='RID_field', datatype='Field', parameterType='Required', direction='Input')
        param_points = arcpy.Parameter(displayName='Output: From points feature class', name='points', datatype='DEFeatureClass', parameterType='Required', direction='Output')
        param_splits = arcpy.Parameter(displayName='Output: Split points feature class', name='splits', datatype='DEFeatureClass', parameterType='Required', direction='Output')

        project_path = arcpy.env.workspace
        param_network_shp.filter.list = ['Polyline']
        if project_path:
            param_network_shp.value = os.path.join(project_path, 'Geometry.gdb', 'routes_main')
            param_links_table.value = os.path.join(project_path, 'Geometry.gdb', 'routes_main_links')
            param_RID_field.value = 'RID'
            param_points.value = os.path.join(project_path, 'Geometry.gdb', 'from_pts')
            param_splits.value = os.path.join(project_path, 'Geometry.gdb', 'splits')
        param_RID_field.parameterDependencies = [param_network_shp.name]
        return [param_network_shp, param_links_table, param_RID_field, param_points, param_splits]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        execute_CreateFromPointsAndSplits(
            parameters[0].valueAsText,
            parameters[1].valueAsText,
            parameters[2].valueAsText,
            parameters[3].valueAsText,
            parameters[4].valueAsText,
            GIStools=ArcGIStools,
            messages=Messages(messages),
        )
        return
