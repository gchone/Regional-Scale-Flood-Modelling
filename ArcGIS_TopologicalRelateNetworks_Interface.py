import os
import arcpy

from TopologicalRelateNetworks import execute_TopologicalRelateNetworks
import ArcGIStools
from ArcGIS_Messages import Messages


class TopologicalRelateNetworks(object):
    def __init__(self):
        self.label = 'Relate a D8 network layer using topological comparison'
        self.description = 'Relate two route layers using upstream topology.'
        self.canRunInBackground = True

    def getParameterInfo(self):
        param_shapefile_A = arcpy.Parameter(displayName='D8 network layer', name='shapefile_A', datatype='DEFeatureClass', parameterType='Required', direction='Input')
        param_RID_A = arcpy.Parameter(displayName='RouteID field in the D8 network layer', name='RID_A', datatype='Field', parameterType='Required', direction='Input')
        param_links_A = arcpy.Parameter(displayName='Input D8 route link table', name='links_A', datatype='GPTableView', parameterType='Required', direction='Input')
        param_shapefile_B = arcpy.Parameter(displayName='Reference network layer', name='shapefile_B', datatype='DEFeatureClass', parameterType='Required', direction='Input')
        param_RID_B = arcpy.Parameter(displayName='RouteID field in the reference network layer', name='RID_B', datatype='Field', parameterType='Required', direction='Input')
        param_links_B = arcpy.Parameter(displayName='Input reference route link table', name='links_B', datatype='GPTableView', parameterType='Required', direction='Input')
        param_fpoints = arcpy.Parameter(displayName='From points', name='fpoints', datatype='DEFeatureClass', parameterType='Required', direction='Input')
        param_out_table = arcpy.Parameter(displayName='Output table', name='out_table', datatype='GPTableView', parameterType='Required', direction='Output')

        project_path = arcpy.env.workspace
        if project_path:
            param_shapefile_A.value = os.path.join(project_path, 'WaterSurface.gdb', 'wsroutesD8')
            param_RID_A.value = 'RID'
            param_links_A.value = os.path.join(project_path, 'WaterSurface.gdb', 'wslinksD8')
            param_shapefile_B.value = os.path.join(project_path, 'Geometry.gdb', 'routes_main')
            param_RID_B.value = 'RID'
            param_links_B.value = os.path.join(project_path, 'Geometry.gdb', 'routes_main_links')
            param_fpoints.value = os.path.join(project_path, 'Geometry.gdb', 'from_pts')
            param_out_table.value = os.path.join(project_path, 'WaterSurface.gdb', 'net_relate_table')
        param_RID_A.parameterDependencies = [param_shapefile_A.name]
        param_RID_B.parameterDependencies = [param_shapefile_B.name]
        return [param_shapefile_A, param_RID_A, param_links_A, param_shapefile_B, param_RID_B, param_links_B, param_fpoints, param_out_table]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        execute_TopologicalRelateNetworks(
            parameters[0].valueAsText,
            parameters[1].valueAsText,
            parameters[2].valueAsText,
            parameters[3].valueAsText,
            parameters[4].valueAsText,
            parameters[5].valueAsText,
            parameters[6].valueAsText,
            parameters[7].valueAsText,
            messages=Messages(messages),
            GIStools=ArcGIStools,
            final_selection='ENDS',
        )
        return


TopologicalD8RelateNetworks = TopologicalRelateNetworks
