import os

import arcpy

import ArcGIStools
from ArcGIS_Messages import Messages
from ExtractWaterSurface import execute_ExtractWaterSurface


class ArcGIS_ExtractWaterSurface_Interface(object):
    def __init__(self):
        self.label = "Extract water surface"
        self.description = ""
        self.canRunInBackground = True

    def getParameterInfo(self):
        param_routes = arcpy.Parameter(
            displayName="Input route feature class (lines)",
            name="routes",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input",
        )
        param_RID_field = arcpy.Parameter(
            displayName="RouteID field in the Input route feature class",
            name="RID_field",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_order_field = arcpy.Parameter(
            displayName="Order field in the Input route feature class (from 'Order reaches tool')",
            name="order_field",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_links = arcpy.Parameter(
            displayName="Input route link table",
            name="links",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input",
        )
        param_fpoints = arcpy.Parameter(
            displayName="From Points",
            name="fpoints",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input",
        )
        param_routes_3m = arcpy.Parameter(
            displayName="Input routes 3m feature class (lines)",
            name="routes_3m",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input",
        )
        param_RID_field_3m = arcpy.Parameter(
            displayName="RouteID field in route 3m feature class",
            name="RID_field_3m",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_links_3m = arcpy.Parameter(
            displayName="Input routes 3m links table",
            name="links_3m",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input",
        )
        param_pts_table = arcpy.Parameter(
            displayName="Points table",
            name="pts_table",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input",
        )
        param_X_field_pts = arcpy.Parameter(
            displayName="Name of X field",
            name="X_field_pts",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_Y_field_pts = arcpy.Parameter(
            displayName="Name of Y field",
            name="Y_field_pts",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_lidar3m_cor = arcpy.Parameter(
            displayName="Lidar 3m cor",
            name="lidar3m_cor",
            datatype="DERasterDataset",
            parameterType="Required",
            direction="Input",
        )
        param_DEMs_footprints = arcpy.Parameter(
            displayName="DEMs footprint feature class",
            name="DEMs_footprints",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input",
        )
        param_DEMs_field = arcpy.Parameter(
            displayName="DEMs field in DEMs footprint feature class",
            name="DEMs_field",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_targets = arcpy.Parameter(
            displayName="Target points to extract water surface",
            name="targets",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input",
        )
        param_targets_id_field = arcpy.Parameter(
            displayName="ID field in the target points table",
            name="targets_id_field",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_targets_rid_field = arcpy.Parameter(
            displayName="Route ID field in the target points table",
            name="targets_rid_field",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_targets_distfield = arcpy.Parameter(
            displayName="Distance field in the target points on network layer",
            name="targets_distfield",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_out_table = arcpy.Parameter(
            displayName="Output: Relate table",
            name="out_table",
            datatype="GPTableView",
            parameterType="Required",
            direction="Output",
        )
        param_output_points = arcpy.Parameter(
            displayName="Output: Points with extracted water surface",
            name="output_points",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output",
        )

        project_path = arcpy.env.workspace
        param_routes.value = os.path.join(project_path, "Geometry.gdb", "routes_main")
        param_RID_field.parameterDependencies = [param_routes.name]
        param_RID_field.value = "RID"
        param_order_field.parameterDependencies = [param_routes.name]
        param_order_field.value = "Qorder"
        param_links.value = os.path.join(project_path, "Geometry.gdb", "routes_main_links")
        param_fpoints.value = os.path.join(project_path, "Geometry.gdb", "from_pts")
        param_routes_3m.value = os.path.join(project_path, "WaterSurface.gdb", "wsroutesD8")
        param_RID_field_3m.parameterDependencies = [param_routes_3m.name]
        param_RID_field_3m.value = "RID"
        param_links_3m.value = os.path.join(project_path, "WaterSurface.gdb", "wslinksD8")
        param_pts_table.value = os.path.join(project_path, "WaterSurface.gdb", "ws_pathpointsD8")
        param_X_field_pts.parameterDependencies = [param_pts_table.name]
        param_X_field_pts.value = "X"
        param_Y_field_pts.parameterDependencies = [param_pts_table.name]
        param_Y_field_pts.value = "Y"
        param_lidar3m_cor.value = os.path.join(project_path, "WaterSurface.gdb", "lidar3m_forws")
        param_DEMs_footprints.value = os.path.join(project_path, "Geometry.gdb", "DEM_footprints")
        param_DEMs_field.parameterDependencies = [param_DEMs_footprints.name]
        param_DEMs_field.value = "ID_DEM"
        param_targets.value = os.path.join(project_path, "Geometry.gdb", "target_pts")
        param_targets_id_field.parameterDependencies = [param_targets.name]
        param_targets_id_field.value = "ObjectID_1"
        param_targets_rid_field.parameterDependencies = [param_targets.name]
        param_targets_rid_field.value = "RID"
        param_targets_distfield.parameterDependencies = [param_targets.name]
        param_targets_distfield.value = "MEAS"
        param_out_table.value = os.path.join(project_path, "WaterSurface.gdb", "net_relate_table")
        param_output_points.value = os.path.join(project_path, "WaterSurface.gdb", "smoothed_pts")

        return [
            param_routes,
            param_RID_field,
            param_order_field,
            param_links,
            param_fpoints,
            param_routes_3m,
            param_RID_field_3m,
            param_links_3m,
            param_pts_table,
            param_X_field_pts,
            param_Y_field_pts,
            param_lidar3m_cor,
            param_DEMs_footprints,
            param_DEMs_field,
            param_targets,
            param_targets_id_field,
            param_targets_rid_field,
            param_targets_distfield,
            param_out_table,
            param_output_points,
        ]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        del parameters
        return

    def updateMessages(self, parameters):
        del parameters
        return

    def execute(self, parameters, messages):
        execute_ExtractWaterSurface(
            parameters[0].valueAsText,
            parameters[3].valueAsText,
            parameters[1].valueAsText,
            parameters[2].valueAsText,
            parameters[4].valueAsText,
            parameters[5].valueAsText,
            parameters[6].valueAsText,
            parameters[7].valueAsText,
            parameters[8].valueAsText,
            parameters[9].valueAsText,
            parameters[10].valueAsText,
            arcpy.Raster(parameters[11].valueAsText),
            parameters[12].valueAsText,
            parameters[13].valueAsText,
            parameters[14].valueAsText,
            parameters[15].valueAsText,
            parameters[16].valueAsText,
            parameters[17].valueAsText,
            parameters[18].valueAsText,
            parameters[19].valueAsText,
            GIStools=ArcGIStools,
            messages=Messages(messages),
        )
        return
