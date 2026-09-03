# -*- coding: utf-8 -*-

import arcpy

from BatchProcessAggregate import execute_BatchProcessAggregate
import ArcGIStools
from ArcGIS_Messages import Messages


class BatchAggregate(object):
    def __init__(self):
        self.label = "Batch process Aggregate"
        self.description = "Batch process the Aggregate tool from a list of rasters"
        self.canRunInBackground = True

    def getParameterInfo(self):
        param_rasters = arcpy.Parameter(
            displayName="Rasters to aggregate",
            name="rasters",
            datatype="GPRasterLayer",
            parameterType="Required",
            direction="Input",
            multiValue=True,
        )
        param_factor = arcpy.Parameter(
            displayName="Cell factor",
            name="factor",
            datatype="GPLong",
            parameterType="Required",
            direction="Input",
        )
        param_tech = arcpy.Parameter(
            displayName="Aggregation technique",
            name="tech",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
        )
        param_extent = arcpy.Parameter(
            displayName="Expand extent if needed",
            name="extent",
            datatype="GPBoolean",
            parameterType="Required",
            direction="Input",
        )
        param_nodata = arcpy.Parameter(
            displayName="Ignore NoData in calculations",
            name="nodata",
            datatype="GPBoolean",
            parameterType="Required",
            direction="Input",
        )
        param_output = arcpy.Parameter(
            displayName="Output location",
            name="output_workspace",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input",
        )

        param_tech.filter.type = "ValueList"
        param_tech.filter.list = ["SUM", "MAXIMUM", "MEAN", "MEDIAN", "MINIMUM"]
        param_tech.value = "MEAN"
        param_extent.value = True
        param_nodata.value = True

        return [param_rasters, param_factor, param_tech, param_extent, param_nodata, param_output]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        del parameters
        return

    def updateMessages(self, parameters):
        del parameters
        return

    def execute(self, parameters, messages):
        rasterlist = parameters[0].valueAsText.split(";")
        extent = "EXPAND" if str(parameters[3].valueAsText).lower() == "true" else "TRUNCATE"
        nodata = "DATA" if str(parameters[4].valueAsText).lower() == "true" else "NODATA"

        execute_BatchProcessAggregate(
            rasterlist,
            int(parameters[1].valueAsText),
            parameters[2].valueAsText,
            extent,
            nodata,
            parameters[5].valueAsText,
            GIStools=ArcGIStools,
            messages=Messages(messages),
        )
        return


ArcGIS_BatchProcessAggregate_Interface = BatchAggregate
