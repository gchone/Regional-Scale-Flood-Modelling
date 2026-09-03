import os
import arcpy

from OrderReaches import execute_OrderReaches
import ArcGIStools
from ArcGIS_Messages import Messages


class OrderReaches(object):
    def __init__(self):
        self.label = 'Order reaches'
        self.description = ''
        self.canRunInBackground = True

    def getParameterInfo(self):
        param_routes = arcpy.Parameter(displayName='Input route feature class (lines)', name='routes', datatype='DEFeatureClass', parameterType='Required', direction='Input')
        param_links = arcpy.Parameter(displayName='Link table', name='links', datatype='GPTableView', parameterType='Required', direction='Input')
        param_RID_field = arcpy.Parameter(displayName='RouteID field', name='RID_field', datatype='Field', parameterType='Required', direction='Input')
        param_r_flowacc = arcpy.Parameter(displayName='Flow accumulation raster', name='r_flowacc', datatype='DERasterDataset', parameterType='Required', direction='Input')
        param_routeD8 = arcpy.Parameter(displayName='Input route D8 feature class (lines)', name='routeD8', datatype='DEFeatureClass', parameterType='Required', direction='Input')
        param_linksD8 = arcpy.Parameter(displayName='Link table', name='linksD8', datatype='GPTableView', parameterType='Required', direction='Input')
        param_ptsonD8 = arcpy.Parameter(displayName='Point on route D8 feature class', name='ptsonD8', datatype='GPTableView', parameterType='Required', direction='Input')
        param_relatetable = arcpy.Parameter(displayName='Relate table', name='relatetable', datatype='GPTableView', parameterType='Required', direction='Input')
        param_outputfield = arcpy.Parameter(displayName='Output field', name='outputfield', datatype='GPString', parameterType='Required', direction='Input')

        project_path = arcpy.env.workspace
        param_routes.filter.list = ['Polyline']
        if project_path:
            param_routes.value = os.path.join(project_path, 'Geometry.gdb', 'routes_main')
            param_links.value = os.path.join(project_path, 'Geometry.gdb', 'routes_main_links')
            param_RID_field.value = 'RID'
            param_r_flowacc.value = os.path.join(project_path, '10mDEMs.gdb', 'lidar10m_facc')
            param_routeD8.value = os.path.join(project_path, 'Geometry.gdb', 'routesD8')
            param_linksD8.value = os.path.join(project_path, 'Geometry.gdb', 'linksD8')
            param_ptsonD8.value = os.path.join(project_path, 'Geometry.gdb', 'pathpointsD8')
            param_relatetable.value = os.path.join(project_path, 'Geometry.gdb', 'fd_net_relatetable')
            param_outputfield.value = 'Qorder'
        param_RID_field.parameterDependencies = [param_routes.name]
        return [param_routes, param_links, param_RID_field, param_r_flowacc, param_routeD8, param_linksD8, param_ptsonD8, param_relatetable, param_outputfield]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        execute_OrderReaches(
            parameters[0].valueAsText,
            parameters[1].valueAsText,
            parameters[2].valueAsText,
            parameters[3].valueAsText,
            parameters[4].valueAsText,
            parameters[5].valueAsText,
            parameters[6].valueAsText,
            parameters[7].valueAsText,
            parameters[8].valueAsText,
            messages=Messages(messages),
            GIStools=ArcGIStools,
        )
        return
