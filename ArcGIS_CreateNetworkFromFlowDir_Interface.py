import os
import arcpy

from CreateNetworkFromFlowDir import execute_CreateNetworkFromFlowDir
import ArcGIStools
from ArcGIS_Messages import Messages


class CreateNetworkFromFlowDir(object):
    def __init__(self):
        self.label = 'Create network from flow direction raster'
        self.description = 'Create a network data structure from a flow direction raster.'
        self.canRunInBackground = True

    def getParameterInfo(self):
        param_r_flowdir = arcpy.Parameter(displayName='Flow direction raster', name='r_flowdir', datatype='DERasterDataset', parameterType='Required', direction='Input')
        param_str_frompoints = arcpy.Parameter(displayName='Upstream ends of the network', name='str_frompoints', datatype='DEFeatureClass', parameterType='Required', direction='Input')
        param_route_shapefile = arcpy.Parameter(displayName='Output: Network layer', name='route_shapefile', datatype='DEFeatureClass', parameterType='Required', direction='Output')
        param_routelinks_table = arcpy.Parameter(displayName='Output: Link table', name='routelinks_table', datatype='GPTableView', parameterType='Required', direction='Output')
        param_routeID_field = arcpy.Parameter(displayName='RouteID field name', name='routeID_field', datatype='GPString', parameterType='Required', direction='Input')
        param_str_output_points = arcpy.Parameter(displayName='Output: Flow direction pixels along flow path output table', name='str_output_points', datatype='DEFeatureClass', parameterType='Required', direction='Output')
        param_split_pts = arcpy.Parameter(displayName='Split points between reaches', name='split_pts', datatype='DEFeatureClass', parameterType='Optional', direction='Input')
        param_tolerance = arcpy.Parameter(displayName='Tolerance between split points and the network, in meters', name='tolerance', datatype='GPDouble', parameterType='Optional', direction='Input')

        project_path = arcpy.env.workspace
        if project_path:
            param_r_flowdir.value = os.path.join(project_path, 'WaterSurface.gdb', 'lidar3m_fd')
            param_str_frompoints.value = os.path.join(project_path, 'Geometry.gdb', 'from_pts')
            param_route_shapefile.value = os.path.join(project_path, 'WaterSurface.gdb', 'wsroutesD8')
            param_routelinks_table.value = os.path.join(project_path, 'WaterSurface.gdb', 'wslinksD8')
            param_routeID_field.value = 'RID'
            param_str_output_points.value = os.path.join(project_path, 'WaterSurface.gdb', 'ws_pathpointsD8')
        return [param_r_flowdir, param_str_frompoints, param_route_shapefile, param_routelinks_table, param_routeID_field, param_str_output_points, param_split_pts, param_tolerance]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        execute_CreateNetworkFromFlowDir(
            arcpy.Raster(parameters[0].valueAsText),
            parameters[1].valueAsText,
            parameters[2].valueAsText,
            parameters[3].valueAsText,
            parameters[4].valueAsText,
            parameters[5].valueAsText,
            parameters[6].valueAsText,
            parameters[7].valueAsText,
            GIStools=ArcGIStools,
            messages=Messages(messages),
        )
        return


TreeFromFlowDir = CreateNetworkFromFlowDir
