import arcpy

import ArcGIStools
from ArcGIS_Messages import Messages
from SpatializeQ import execute_SpatializeQ


class SpatializeQ(object):
    def __init__(self):
        self.label = 'SpatializeQ Tool'
        self.description = ''
        self.canRunInBackground = True

    def getParameterInfo(self):
        param_route_D8 = arcpy.Parameter(displayName='Input route D8 feature class (lines)', name='route_D8', datatype='DEFeatureClass', parameterType='Required', direction='Input')
        param_RID_field_D8 = arcpy.Parameter(displayName='RouteID field', name='RID_field_D8', datatype='Field', parameterType='Required', direction='Input')
        param_D8pathpoints = arcpy.Parameter(displayName='D8 Pathpoints', name='D8pathpoints', datatype='GPTableView', parameterType='Required', direction='Input')
        param_relate_table = arcpy.Parameter(displayName='Relate table', name='relate_table', datatype='GPTableView', parameterType='Required', direction='Input')
        param_r_flowacc = arcpy.Parameter(displayName='Flow Accumulation raster', name='r_flowacc', datatype='DERasterDataset', parameterType='Required', direction='Input')
        param_routes = arcpy.Parameter(displayName='Input route feature class (lines)', name='routes', datatype='DEFeatureClass', parameterType='Required', direction='Input')
        param_links = arcpy.Parameter(displayName='Routes links', name='links', datatype='GPTableView', parameterType='Required', direction='Input')
        param_RID_field = arcpy.Parameter(displayName='RID field in routes feature class', name='RID_field', datatype='Field', parameterType='Required', direction='Input')
        param_Qorder_field = arcpy.Parameter(displayName='Ordering field in routes feature class', name='Qorder_field', datatype='Field', parameterType='Required', direction='Input')
        param_Qpoints = arcpy.Parameter(displayName='Qpoints', name='Qpoints', datatype='GPTableView', parameterType='Required', direction='Input')
        param_id_field_Qpoints = arcpy.Parameter(displayName='Id field in Qpoints', name='id_field_Qpoints', datatype='Field', parameterType='Required', direction='Input')
        param_RID_Qpoints = arcpy.Parameter(displayName='RID field in Qpoints', name='RID_Qpoints', datatype='Field', parameterType='Required', direction='Input')
        param_dist_field_Qpoints = arcpy.Parameter(displayName='MEAS field in Qpoints', name='dist_field_Qpoints', datatype='Field', parameterType='Required', direction='Input')
        param_AtlasReach_field_Qpoints = arcpy.Parameter(displayName='AtlasReach field in Qpoints', name='AtlasReach_field_Qpoints', datatype='Field', parameterType='Required', direction='Input')
        param_targetpoints = arcpy.Parameter(displayName='Target points', name='targetpoints', datatype='GPTableView', parameterType='Required', direction='Input')
        param_id_field_target = arcpy.Parameter(displayName='ID field in target points feature class', name='id_field_target', datatype='Field', parameterType='Required', direction='Input')
        param_RID_field_target = arcpy.Parameter(displayName='RID field in target points feature class', name='RID_field_target', datatype='Field', parameterType='Required', direction='Input')
        param_Distance_field_target = arcpy.Parameter(displayName='MEAS field in target points feature class', name='Distance_field_target', datatype='Field', parameterType='Required', direction='Input')
        param_DEM_field_target = arcpy.Parameter(displayName='DEM field in target points feature class', name='DEM_field_target', datatype='Field', parameterType='Required', direction='Input')
        param_Qcsv_file = arcpy.Parameter(displayName='Qcsv_file', name='Qcsv_file', datatype='GPTableView', parameterType='Required', direction='Input')
        param_output_points = arcpy.Parameter(displayName='Points Output table', name='output_points', datatype='GPTableView', parameterType='Required', direction='Output')

        param_RID_field_D8.parameterDependencies = [param_route_D8.name]
        param_RID_field.parameterDependencies = [param_routes.name]
        param_Qorder_field.parameterDependencies = [param_routes.name]
        param_id_field_Qpoints.parameterDependencies = [param_Qpoints.name]
        param_RID_Qpoints.parameterDependencies = [param_Qpoints.name]
        param_dist_field_Qpoints.parameterDependencies = [param_Qpoints.name]
        param_AtlasReach_field_Qpoints.parameterDependencies = [param_Qpoints.name]
        param_id_field_target.parameterDependencies = [param_targetpoints.name]
        param_RID_field_target.parameterDependencies = [param_targetpoints.name]
        param_Distance_field_target.parameterDependencies = [param_targetpoints.name]
        param_DEM_field_target.parameterDependencies = [param_targetpoints.name]

        return [param_route_D8, param_RID_field_D8, param_D8pathpoints, param_relate_table, param_r_flowacc, param_routes, param_links, param_RID_field, param_Qorder_field, param_Qpoints, param_id_field_Qpoints, param_RID_Qpoints, param_dist_field_Qpoints, param_AtlasReach_field_Qpoints, param_targetpoints, param_id_field_target, param_RID_field_target, param_Distance_field_target, param_DEM_field_target, param_Qcsv_file, param_output_points]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        del parameters
        return

    def updateMessages(self, parameters):
        del parameters
        return

    def execute(self, parameters, messages):
        execute_SpatializeQ(
            parameters[0].valueAsText,
            parameters[1].valueAsText,
            parameters[2].valueAsText,
            parameters[3].valueAsText,
            arcpy.Raster(parameters[4].valueAsText),
            parameters[5].valueAsText,
            parameters[6].valueAsText,
            parameters[7].valueAsText,
            parameters[8].valueAsText,
            parameters[9].valueAsText,
            parameters[10].valueAsText,
            parameters[11].valueAsText,
            parameters[12].valueAsText,
            parameters[13].valueAsText,
            parameters[14].valueAsText,
            parameters[15].valueAsText,
            parameters[16].valueAsText,
            parameters[17].valueAsText,
            parameters[18].valueAsText,
            parameters[19].valueAsText,
            parameters[20].valueAsText,
            messages=Messages(messages),
            GIStools=ArcGIStools,
        )
        return


ArcGIS_SpatializeQ_Interface = SpatializeQ
