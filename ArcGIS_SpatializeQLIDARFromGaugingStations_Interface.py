import os

import arcpy

import ArcGIStools
from ArcGIS_Messages import Messages
from SpatializeQLIDARFromGaugingStations import execute_SpatializeQLIDARFromGaugingStations


class SpatializeQLIDARFromGaugingStations(object):
    def __init__(self):
        self.label = 'Spatialize discharges from gauging stations - Q LiDAR'
        self.description = ''
        self.canRunInBackground = True

    def getParameterInfo(self):
        param_r_flowacc = arcpy.Parameter(displayName='Flow Accumulation raster', name='r_flowacc', datatype='DERasterDataset', parameterType='Required', direction='Input')
        param_routes = arcpy.Parameter(displayName='Input D8 route feature class', name='routes', datatype='DEFeatureClass', parameterType='Required', direction='Input')
        param_RID_field = arcpy.Parameter(displayName='RID field in routes feature class', name='RID_field', datatype='Field', parameterType='Required', direction='Input')
        param_links = arcpy.Parameter(displayName='Routes D8 links', name='links', datatype='GPTableView', parameterType='Required', direction='Input')
        param_ptsonD8 = arcpy.Parameter(displayName='Point on route D8', name='ptsonD8', datatype='GPTableView', parameterType='Required', direction='Input')
        param_Qpoints = arcpy.Parameter(displayName='Qpoints', name='Qpoints', datatype='DEFeatureClass', parameterType='Required', direction='Input')
        param_id_field_Qpoints = arcpy.Parameter(displayName='Id field in Qpoints', name='id_field_Qpoints', datatype='Field', parameterType='Required', direction='Input')
        param_name_Qpoints = arcpy.Parameter(displayName='Gauging station name in Qpoints', name='name_Qpoints', datatype='Field', parameterType='Required', direction='Input')
        param_drainage_Qpoints = arcpy.Parameter(displayName='Drainage area in Qpoints', name='drainage_Qpoints', datatype='Field', parameterType='Required', direction='Input')
        param_Qdistance = arcpy.Parameter(displayName='Maximum distance of gauging stations to the river (m)', name='Qdistance', datatype='GPDouble', parameterType='Required', direction='Input')
        param_Qcsv_file = arcpy.Parameter(displayName='Qcsv_file', name='Qcsv_file', datatype='GPTableView', parameterType='Required', direction='Input')
        param_DEMs_footprints = arcpy.Parameter(displayName='DEMs footprint feature class', name='DEMs_footprints', datatype='DEFeatureClass', parameterType='Required', direction='Input')
        param_DEMs_field = arcpy.Parameter(displayName='DEM id field in DEMs footprint feature class', name='DEMs_field', datatype='Field', parameterType='Required', direction='Input')
        param_beta = arcpy.Parameter(displayName='Beta coefficient', name='Beta', datatype='GPDouble', parameterType='Required', direction='Input')
        param_relatetable = arcpy.Parameter(displayName='Relate table - Main routes to D8 correspondence', name='relatetable', datatype='GPTableView', parameterType='Required', direction='Input')
        param_output_points = arcpy.Parameter(displayName='Output: Points with spatialized Q', name='output_points', datatype='DEFeatureClass', parameterType='Required', direction='Output')

        project_path = arcpy.env.workspace
        param_routes.filter.list = ['Polyline']
        param_DEMs_footprints.filter.list = ['Polygon']
        if project_path not in [None, '']:
            param_r_flowacc.value = os.path.join(project_path, '10mDEMs.gdb', 'lidar10m_facc')
            param_routes.value = os.path.join(project_path, 'Geometry.gdb', 'routesD8')
            param_RID_field.value = 'RID'
            param_links.value = os.path.join(project_path, 'Geometry.gdb', 'linksD8')
            param_ptsonD8.value = os.path.join(project_path, 'Geometry.gdb', 'pathpointsD8')
            param_Qpoints.value = os.path.join(project_path, 'Gauging_stations.gdb', 'QStations _D8')
            param_Qdistance.value = 500.0
            param_DEMs_footprints.value = os.path.join(project_path, 'Geometry.gdb', 'DEM_footprints')
            param_DEMs_field.value = 'ID_DEM'
            param_beta.value = 1.0
            param_relatetable.value = os.path.join(project_path, 'Geometry.gdb', 'fd_net_relatetable')
            param_output_points.value = os.path.join(project_path, 'Discharge.gdb', 'Qpts_spatialized_D8')

        param_RID_field.parameterDependencies = [param_routes.name]
        param_id_field_Qpoints.parameterDependencies = [param_Qpoints.name]
        param_name_Qpoints.parameterDependencies = [param_Qpoints.name]
        param_drainage_Qpoints.parameterDependencies = [param_Qpoints.name]
        param_DEMs_field.parameterDependencies = [param_DEMs_footprints.name]

        return [param_r_flowacc, param_routes, param_RID_field, param_links, param_ptsonD8, param_Qpoints, param_id_field_Qpoints, param_name_Qpoints, param_drainage_Qpoints, param_Qdistance, param_Qcsv_file, param_DEMs_footprints, param_DEMs_field, param_beta, param_relatetable, param_output_points]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        del parameters
        return

    def updateMessages(self, parameters):
        del parameters
        return

    def execute(self, parameters, messages):
        execute_SpatializeQLIDARFromGaugingStations(
            parameters[1].valueAsText,
            parameters[3].valueAsText,
            parameters[2].valueAsText,
            parameters[4].valueAsText,
            arcpy.Raster(parameters[0].valueAsText),
            parameters[5].valueAsText,
            parameters[6].valueAsText,
            parameters[7].valueAsText,
            parameters[8].valueAsText,
            float(parameters[9].valueAsText),
            parameters[10].valueAsText,
            parameters[11].valueAsText,
            parameters[12].valueAsText,
            float(parameters[13].valueAsText),
            parameters[14].valueAsText,
            parameters[15].valueAsText,
            messages=Messages(messages),
            GIStools=ArcGIStools,
        )
        return


ArcGIS_SpatializeQLIDARFromGaugingStations_Interface = SpatializeQLIDARFromGaugingStations
