import os
import arcpy

from CreateNetworkFromFC import execute_CreateNetworkFromFC
import ArcGIStools
from ArcGIS_Messages import Messages


class CreateNetworkFromFC(object):
    def __init__(self):
        self.label = 'Create network from feature class'
        self.description = 'Create a river network data structure from a line feature class.'
        self.canRunInBackground = True

    def getParameterInfo(self):
        param_config = arcpy.Parameter(displayName='Configuration', name='config', datatype='GPString', parameterType='Required', direction='Input')
        param_rivernet = arcpy.Parameter(displayName='Input feature class (lines)', name='rivernet', datatype='DEFeatureClass', parameterType='Required', direction='Input')
        param_route_shapefile = arcpy.Parameter(displayName='Output: Network layer', name='route_shapefile', datatype='DEFeatureClass', parameterType='Required', direction='Output')
        param_routelinks_table = arcpy.Parameter(displayName='Output: Link table (DownRouteID-UpRouteID)', name='routelinks_table', datatype='GPTableView', parameterType='Required', direction='Output')
        param_routeID_field = arcpy.Parameter(displayName='RouteID field', name='routeID_field', datatype='Field', parameterType='Required', direction='Input')
        param_downstream_reach_field = arcpy.Parameter(displayName='Field identifying the most downstream reach', name='downstream_reach_field', datatype='Field', parameterType='Required', direction='Input')
        param_channeltype_field = arcpy.Parameter(displayName='Field identifying the main or secondary channel', name='channeltype_field', datatype='Field', parameterType='Optional', direction='Input')

        project_path = arcpy.env.workspace
        param_config.filter.type = 'ValueList'
        param_config.filter.list = ['Main channel only', 'With secondary channels', 'Custom']
        param_config.value = 'Custom'
        param_rivernet.filter.list = ['Polyline']
        param_routeID_field.parameterDependencies = [param_rivernet.name]
        param_downstream_reach_field.parameterDependencies = [param_rivernet.name]
        param_channeltype_field.parameterDependencies = [param_rivernet.name]

        param_rivernet.category = 'Parameters'
        param_routeID_field.category = 'Parameters'
        param_downstream_reach_field.category = 'Parameters'
        param_channeltype_field.category = 'Parameters'
        param_route_shapefile.category = 'Parameters'
        param_routelinks_table.category = 'Parameters'

        if project_path:
            pass
        return [param_config, param_rivernet, param_route_shapefile, param_routelinks_table, param_routeID_field, param_downstream_reach_field, param_channeltype_field]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        project_path = arcpy.env.workspace
        if project_path and not parameters[0].hasBeenValidated:
            if parameters[0].valueAsText == 'Main channel only':
                parameters[1].value = os.path.join(project_path, 'Geometry.gdb', 'linear_main_d')
                parameters[4].value = 'RID'
                parameters[5].value = 'DownEnd'
                parameters[6].value = None
                parameters[2].value = os.path.join(project_path, 'Geometry.gdb', 'routes_main')
                parameters[3].value = os.path.join(project_path, 'Geometry.gdb', 'routes_main_links')
            if parameters[0].valueAsText == 'With secondary channels':
                parameters[1].value = os.path.join(project_path, 'Geometry.gdb', 'linear_net_d')
                parameters[4].value = 'RID'
                parameters[5].value = 'DownEnd'
                parameters[6].value = 'Main'
                parameters[2].value = os.path.join(project_path, 'Geometry.gdb', 'routes')
                parameters[3].value = os.path.join(project_path, 'Geometry.gdb', 'routes_links')
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        execute_CreateNetworkFromFC(
            parameters[1].valueAsText,
            parameters[2].valueAsText,
            parameters[3].valueAsText,
            parameters[4].valueAsText,
            parameters[5].valueAsText,
            parameters[6].valueAsText,
            GIStools=ArcGIStools,
            messages=Messages(messages),
        )
        return


CreateTreeFromShapefile = CreateNetworkFromFC
