import os

import arcpy

import ArcGIStools
from ArcGIS_Messages import Messages
from WatershedScaleDEMprocessing import execute_WatershedScaleDEMprocessing


class ArcGIS_WatershedScaleDEMprocessing_Interface(object):
    def __init__(self):
        self.label = "Watershed-scale DEM processing"
        self.description = ""
        self.canRunInBackground = True

    def getParameterInfo(self):
        param_poly = arcpy.Parameter(
            displayName="Polygons of the river network",
            name="poly",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input",
        )
        param_lines_toburn = arcpy.Parameter(
            displayName="River network for stream burning",
            name="lines_toburn",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input",
        )
        param_DEMavg = arcpy.Parameter(
            displayName="DEM raster, 10m resolution",
            name="DEMavg",
            datatype="DERasterDataset",
            parameterType="Required",
            direction="Input",
        )
        param_riverlines = arcpy.Parameter(
            displayName="River network",
            name="riverlines",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input",
        )
        param_riverlinesmain = arcpy.Parameter(
            displayName="River network - main channels only",
            name="riverlinesmain",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input",
        )
        param_toburnfrompoly = arcpy.Parameter(
            displayName="Output: Mask raster from polygons",
            name="toburnfrompoly",
            datatype="DERasterDataset",
            parameterType="Required",
            direction="Output",
        )
        param_toburnfromlines = arcpy.Parameter(
            displayName="Output: Rasterized lines (for stream burning)",
            name="toburnfromlines",
            datatype="DERasterDataset",
            parameterType="Required",
            direction="Output",
        )
        param_burnedDEM = arcpy.Parameter(
            displayName="Output: Burned DEM raster",
            name="burnedDEM",
            datatype="DERasterDataset",
            parameterType="Required",
            direction="Output",
        )
        param_fillDEM = arcpy.Parameter(
            displayName="Output: Filled DEM raster",
            name="fillDEM",
            datatype="DERasterDataset",
            parameterType="Required",
            direction="Output",
        )
        param_flowdirDEM = arcpy.Parameter(
            displayName="Output: Flow direction raster",
            name="flowdirDEM",
            datatype="DERasterDataset",
            parameterType="Required",
            direction="Output",
        )
        param_flowaccDEM = arcpy.Parameter(
            displayName="Output: Flow accumulation raster",
            name="flowaccDEM",
            datatype="DERasterDataset",
            parameterType="Required",
            direction="Output",
        )
        param_routes = arcpy.Parameter(
            displayName="Output: Rivers route feature class",
            name="routes",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output",
        )
        param_links = arcpy.Parameter(
            displayName="Output: Link table",
            name="links",
            datatype="GPTableView",
            parameterType="Required",
            direction="Output",
        )
        param_routes_main = arcpy.Parameter(
            displayName="Output: Rivers route feature class (main channels only)",
            name="routes_main",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output",
        )
        param_main_links = arcpy.Parameter(
            displayName="Output: Link table (main channels only)",
            name="main_links",
            datatype="GPTableView",
            parameterType="Required",
            direction="Output",
        )
        param_routeD8 = arcpy.Parameter(
            displayName="Output: Route D8 feature class",
            name="routeD8",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output",
        )
        param_linksD8 = arcpy.Parameter(
            displayName="Output: Link table",
            name="linksD8",
            datatype="GPTableView",
            parameterType="Required",
            direction="Output",
        )
        param_ptsonD8 = arcpy.Parameter(
            displayName="Output: Point on route D8 feature class",
            name="ptsonD8",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output",
        )
        param_relatetable = arcpy.Parameter(
            displayName="Output: Relate table",
            name="relatetable",
            datatype="GPTableView",
            parameterType="Required",
            direction="Output",
        )

        project_path = arcpy.env.workspace
        param_poly.filter.list = ["Polygon"]
        param_lines_toburn.filter.list = ["Polyline"]
        param_riverlines.filter.list = ["Polyline"]
        param_riverlinesmain.filter.list = ["Polyline"]
        param_routes.filter.list = ["Polyline"]

        if project_path:
            param_poly.value = os.path.join(project_path, "Geometry.gdb", "channelpoly")
            param_lines_toburn.value = os.path.join(project_path, "Geometry.gdb", "watershed_net")
            param_DEMavg.value = os.path.join(project_path, "10mDEMs.gdb", "lidar10m_avg")
            param_riverlines.value = os.path.join(project_path, "Geometry.gdb", "linear_net_d")
            param_riverlinesmain.value = os.path.join(project_path, "Geometry.gdb", "linear_main_d")
            param_toburnfrompoly.value = os.path.join(project_path, "Mask.gdb", "frompoly")
            param_toburnfromlines.value = os.path.join(project_path, "10mDEMs.gdb", "net_lines")
            param_burnedDEM.value = os.path.join(project_path, "10mDEMs.gdb", "lidar10m_burn")
            param_fillDEM.value = os.path.join(project_path, "10mDEMs.gdb", "lidar10m_fill")
            param_flowdirDEM.value = os.path.join(project_path, "10mDEMs.gdb", "lidar10m_fd")
            param_flowaccDEM.value = os.path.join(project_path, "10mDEMs.gdb", "lidar10m_facc")
            param_routes.value = os.path.join(project_path, "Geometry.gdb", "routes")
            param_links.value = os.path.join(project_path, "Geometry.gdb", "routes_links")
            param_routes_main.value = os.path.join(project_path, "Geometry.gdb", "routes_main")
            param_main_links.value = os.path.join(project_path, "Geometry.gdb", "routes_main_links")
            param_routeD8.value = os.path.join(project_path, "Geometry.gdb", "routesD8")
            param_linksD8.value = os.path.join(project_path, "Geometry.gdb", "linksD8")
            param_ptsonD8.value = os.path.join(project_path, "Geometry.gdb", "pathpointsD8")
            param_relatetable.value = os.path.join(project_path, "Geometry.gdb", "fd_net_relatetable")

        return [
            param_poly,
            param_lines_toburn,
            param_DEMavg,
            param_riverlines,
            param_riverlinesmain,
            param_toburnfrompoly,
            param_toburnfromlines,
            param_burnedDEM,
            param_fillDEM,
            param_flowdirDEM,
            param_flowaccDEM,
            param_routes,
            param_links,
            param_routes_main,
            param_main_links,
            param_routeD8,
            param_linksD8,
            param_ptsonD8,
            param_relatetable,
        ]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        execute_WatershedScaleDEMprocessing(
            arcpy.Raster(parameters[2].valueAsText),
            parameters[1].valueAsText,
            parameters[0].valueAsText,
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
            "RID",
            "DownEnd",
            "Main",
            "Qorder",
            messages=Messages(messages),
            GIStools=ArcGIStools,
        )
        return
