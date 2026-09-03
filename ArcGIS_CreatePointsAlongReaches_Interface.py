import os
import arcpy

from CreatePointsAlongReaches import execute_CreatePointsAlongReaches
import ArcGIStools
from ArcGIS_Messages import Messages


class CreatePointsAlongReaches(object):
    def __init__(self):
        self.label = 'Create points along route feature class'
        self.description = 'Create points on a network based on a fixed interval.'
        self.canRunInBackground = True

    def getParameterInfo(self):
        param_network_shp = arcpy.Parameter(displayName='Route feature class', name='network_shp', datatype='DEFeatureClass', parameterType='Required', direction='Input')
        param_links_table = arcpy.Parameter(displayName='Route links table', name='links_table', datatype='GPTableView', parameterType='Required', direction='Input')
        param_RID_field = arcpy.Parameter(displayName='RouteID field in network feature class', name='RID_field', datatype='Field', parameterType='Required', direction='Input')
        param_interval = arcpy.Parameter(displayName='Interval between points, in meters', name='interval', datatype='GPDouble', parameterType='Required', direction='Input')
        param_output_pt = arcpy.Parameter(displayName='Output: Point table', name='output_pt', datatype='GPTableView', parameterType='Required', direction='Output')

        project_path = arcpy.env.workspace
        param_network_shp.filter.list = ['Polyline']
        if project_path:
            param_network_shp.value = os.path.join(project_path, 'Geometry.gdb', 'routes_main')
            param_links_table.value = os.path.join(project_path, 'Geometry.gdb', 'routes_main_links')
            param_RID_field.value = 'RID'
            param_interval.value = 5.0
            param_output_pt.value = os.path.join(project_path, 'Geometry.gdb', 'target_pts_raw')
        param_RID_field.parameterDependencies = [param_network_shp.name]
        return [param_network_shp, param_links_table, param_RID_field, param_interval, param_output_pt]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        execute_CreatePointsAlongReaches(
            parameters[0].valueAsText,
            parameters[1].valueAsText,
            parameters[2].valueAsText,
            float(parameters[3].valueAsText),
            parameters[4].valueAsText,
            GIStools=ArcGIStools,
            messages=Messages(messages),
        )
        return


PlacePointsAlongReaches = CreatePointsAlongReaches
