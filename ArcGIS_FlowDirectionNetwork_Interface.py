import os
import arcpy

from FlowDirectionNetwork import execute_FlowDirectionNetwork
import ArcGIStools
from ArcGIS_Messages import Messages


class FlowDirectionNetwork(object):
    def __init__(self):
        self.label = 'Flow Direction Network'
        self.description = ''
        self.canRunInBackground = True

    def getParameterInfo(self):
        param_routes = arcpy.Parameter(displayName='Input route feature class', name='routes', datatype='DEFeatureClass', parameterType='Required', direction='Input')
        param_links = arcpy.Parameter(displayName='Link table', name='links', datatype='GPTableView', parameterType='Required', direction='Input')
        param_RID_field = arcpy.Parameter(displayName='RouteID field', name='RID_field', datatype='Field', parameterType='Required', direction='Input')
        param_r_flow_dir = arcpy.Parameter(displayName='Flow direction raster', name='r_flow_dir', datatype='DERasterDataset', parameterType='Required', direction='Input')
        param_routeD8 = arcpy.Parameter(displayName='Output: Route D8 feature class', name='routeD8', datatype='DEFeatureClass', parameterType='Required', direction='Output')
        param_linksD8 = arcpy.Parameter(displayName='Output: Link table', name='linksD8', datatype='GPTableView', parameterType='Required', direction='Output')
        param_ptsonD8 = arcpy.Parameter(displayName='Output: Point on route D8 feature class', name='ptsonD8', datatype='DEFeatureClass', parameterType='Required', direction='Output')
        param_relatetable = arcpy.Parameter(displayName='Output: Relate table', name='relatetable', datatype='GPTableView', parameterType='Required', direction='Output')

        project_path = arcpy.env.workspace
        param_routes.filter.list = ['Polyline']
        if project_path:
            param_routes.value = os.path.join(project_path, 'Geometry.gdb', 'routes_main')
            param_links.value = os.path.join(project_path, 'Geometry.gdb', 'routes_main_links')
            param_RID_field.value = 'RID'
            param_r_flow_dir.value = os.path.join(project_path, '10mDEMs.gdb', 'lidar10m_fd')
            param_routeD8.value = os.path.join(project_path, 'Geometry.gdb', 'routesD8')
            param_linksD8.value = os.path.join(project_path, 'Geometry.gdb', 'linksD8')
            param_ptsonD8.value = os.path.join(project_path, 'Geometry.gdb', 'pathpointsD8')
            param_relatetable.value = os.path.join(project_path, 'Geometry.gdb', 'fd_net_relatetable')
        param_RID_field.parameterDependencies = [param_routes.name]
        return [param_routes, param_links, param_RID_field, param_r_flow_dir, param_routeD8, param_linksD8, param_ptsonD8, param_relatetable]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        execute_FlowDirectionNetwork(
            parameters[0].valueAsText,
            parameters[1].valueAsText,
            parameters[2].valueAsText,
            arcpy.Raster(parameters[3].valueAsText),
            parameters[4].valueAsText,
            parameters[5].valueAsText,
            parameters[6].valueAsText,
            parameters[7].valueAsText,
            messages=Messages(messages),
            GIStools=ArcGIStools,
        )
        return


FlowDirNetwork = FlowDirectionNetwork
