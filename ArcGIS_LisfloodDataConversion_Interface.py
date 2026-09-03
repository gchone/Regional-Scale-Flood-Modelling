import os

import arcpy

import ArcGIStools
from ArcGIS_Messages import Messages
from LisfloodDataConversion import execute_LisfloodDataConversion


class ArcGIS_LisfloodDataConversion_Interface(object):
    def __init__(self):
        self.label = "D4 flow direction and Lisflood data conversion"
        self.description = "Automates the preparation of Lisflood inputs, including D4 flow direction, network extraction, and bathymetry/width processing."
        self.canRunInBackground = True

    def getParameterInfo(self):
        param_lidar10m_fd = arcpy.Parameter(
            displayName="Flow Direction Raster",
            name="lidar10m_fd",
            datatype="DERasterDataset",
            parameterType="Required",
            direction="Input",
        )
        param_lidar10m_fill = arcpy.Parameter(
            displayName="Filled DEM",
            name="lidar10m_fill",
            datatype="DERasterDataset",
            parameterType="Required",
            direction="Input",
        )
        param_from_pts = arcpy.Parameter(
            displayName="From points",
            name="from_pts",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input",
        )
        param_workspace = arcpy.Parameter(
            displayName="Temp folder",
            name="workspace",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input",
        )
        param_routes_main = arcpy.Parameter(
            displayName="Main Routes",
            name="routes_main",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input",
        )
        param_routes_main_links = arcpy.Parameter(
            displayName="Main Route Links",
            name="routes_main_links",
            datatype="DETable",
            parameterType="Required",
            direction="Input",
        )
        param_routes_RID_field = arcpy.Parameter(
            displayName="Route ID Field",
            name="routes_RID_field",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_routes_QOrder_field = arcpy.Parameter(
            displayName="Route QOrder Field",
            name="routes_QOrder_field",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_bathy_pts = arcpy.Parameter(
            displayName="Bathymetry Points",
            name="bathy_pts",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input",
        )
        param_bathy_value_field = arcpy.Parameter(
            displayName="Bathymetry Value Field",
            name="bathy_value_field",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_bathy_RID_field = arcpy.Parameter(
            displayName="Bathymetry RID Field",
            name="bathy_RID_field",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_bathy_dist_field = arcpy.Parameter(
            displayName="Bathymetry Distance Field",
            name="bathy_dist_field",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_width_pts = arcpy.Parameter(
            displayName="Width Points",
            name="width_pts",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input",
        )
        param_width_value_field = arcpy.Parameter(
            displayName="Width Value Field",
            name="width_value_field",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_width_RID_field = arcpy.Parameter(
            displayName="Width RID Field",
            name="width_RID_field",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_width_dist_field = arcpy.Parameter(
            displayName="Width Distance Field",
            name="width_dist_field",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_d4fd = arcpy.Parameter(
            displayName="D4 Flow Direction Raster",
            name="d4fd",
            datatype="DERasterDataset",
            parameterType="Required",
            direction="Output",
        )
        param_routesD4 = arcpy.Parameter(
            displayName="D4 Routes",
            name="routesD4",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output",
        )
        param_linksD4 = arcpy.Parameter(
            displayName="D4 Links",
            name="linksD4",
            datatype="DETable",
            parameterType="Required",
            direction="Output",
        )
        param_pathpointsD4 = arcpy.Parameter(
            displayName="D4 Path Points",
            name="pathpointsD4",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output",
        )
        param_D4fd_net_relatetable = arcpy.Parameter(
            displayName="D4fd Net Relate Table",
            name="D4fd_net_relatetable",
            datatype="DETable",
            parameterType="Required",
            direction="Output",
        )
        param_bathy_output_raster = arcpy.Parameter(
            displayName="Output: Bathymetry raster for Lisflood",
            name="bathy_output_raster",
            datatype="DERasterDataset",
            parameterType="Required",
            direction="Output",
        )
        param_width_output_raster = arcpy.Parameter(
            displayName="Output: Width raster for Lisflood",
            name="width_output_raster",
            datatype="DERasterDataset",
            parameterType="Required",
            direction="Output",
        )

        project_root = arcpy.env.workspace
        param_workspace.filter.list = ["File System"]
        if project_root:
            param_lidar10m_fd.value = os.path.join(project_root, "10mDEMs.gdb", "lidar10m_fd")
            param_lidar10m_fill.value = os.path.join(project_root, "10mDEMs.gdb", "lidar10m_fill")
            param_from_pts.value = os.path.join(project_root, "Geometry.gdb", "from_pts")
            param_workspace.value = os.path.join(project_root, "temp")
            param_routes_main.value = os.path.join(project_root, "Geometry.gdb", "routes_main")
            param_routes_main_links.value = os.path.join(project_root, "Geometry.gdb", "routes_main_links")
            param_bathy_pts.value = os.path.join(project_root, "Bathy.gdb", "bathy_pts")
            param_width_pts.value = os.path.join(project_root, "Width.gdb", "width_postpro")
            param_d4fd.value = os.path.join(project_root, "Lisflood_inputs.gdb", "d4fd")
            param_routesD4.value = os.path.join(project_root, "Lisflood_inputs.gdb", "routesD4")
            param_linksD4.value = os.path.join(project_root, "Lisflood_inputs.gdb", "linksD4")
            param_pathpointsD4.value = os.path.join(project_root, "Lisflood_inputs.gdb", "pathpointsD4")
            param_D4fd_net_relatetable.value = os.path.join(project_root, "Lisflood_inputs.gdb", "d4fd_net_relatetable")
            param_bathy_output_raster.value = os.path.join(project_root, "Lisflood_inputs", "bathy_lisflood.tif")
            param_width_output_raster.value = os.path.join(project_root, "Lisflood_inputs", "width_lisflood.tif")

        param_routes_RID_field.parameterDependencies = [param_routes_main.name]
        param_routes_RID_field.value = "RID"
        param_routes_QOrder_field.parameterDependencies = [param_routes_main.name]
        param_routes_QOrder_field.value = "Qorder"
        param_bathy_value_field.parameterDependencies = [param_bathy_pts.name]
        param_bathy_value_field.value = "z"
        param_bathy_RID_field.parameterDependencies = [param_bathy_pts.name]
        param_bathy_RID_field.value = "RID"
        param_bathy_dist_field.parameterDependencies = [param_bathy_pts.name]
        param_bathy_dist_field.value = "MEAS"
        param_width_value_field.parameterDependencies = [param_width_pts.name]
        param_width_value_field.value = "Width_m"
        param_width_RID_field.parameterDependencies = [param_width_pts.name]
        param_width_RID_field.value = "RID"
        param_width_dist_field.parameterDependencies = [param_width_pts.name]
        param_width_dist_field.value = "MEAS"

        return [
            param_lidar10m_fd,
            param_lidar10m_fill,
            param_from_pts,
            param_workspace,
            param_routes_main,
            param_routes_main_links,
            param_routes_RID_field,
            param_routes_QOrder_field,
            param_bathy_pts,
            param_bathy_value_field,
            param_bathy_RID_field,
            param_bathy_dist_field,
            param_width_pts,
            param_width_value_field,
            param_width_RID_field,
            param_width_dist_field,
            param_d4fd,
            param_routesD4,
            param_linksD4,
            param_pathpointsD4,
            param_D4fd_net_relatetable,
            param_bathy_output_raster,
            param_width_output_raster,
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
        execute_LisfloodDataConversion(
            arcpy.Raster(parameters[0].valueAsText),
            arcpy.Raster(parameters[1].valueAsText),
            parameters[2].valueAsText,
            parameters[3].valueAsText,
            parameters[4].valueAsText,
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
            parameters[21].valueAsText,
            parameters[22].valueAsText,
            messages=Messages(messages),
            GIStools=ArcGIStools,
        )
        return
