# -*- coding: utf-8 -*-

import arcpy
from DEMprocessing import execute_BatchAggregate

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
            multiValue=True)
        param_factor = arcpy.Parameter(
            displayName="Cell factor",
            name="factor",
            datatype="GPLong",
            parameterType="Required",
            direction="Input")
        param_tech = arcpy.Parameter(
            displayName="Aggregation technique",
            name="tech",
            datatype="GPString",
            parameterType="Required",
            direction="Output")
        param_extent = arcpy.Parameter(
            displayName="Expand extent if needed",
            name="extent",
            datatype="GPBoolean",
            parameterType="Required",
            direction="Input")
        param_nodata = arcpy.Parameter(
            displayName="Ignore NoData in calculations",
            name="nodata",
            datatype="GPBoolean",
            parameterType="Required",
            direction="Input")
        param_output = arcpy.Parameter(
            displayName="Output location",
            name="output_workspace",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input")


        #param_tech.columns = [["String", "Statistic"]]
        #param_tech.filters[0].type = "ValueList"
        #param_tech.filters[0].list = ["SUM", "MAXIMUM", "MEAN", "MEDIAN", "MINIMUM"]
        param_tech.filter.type = "ValueList"
        param_tech.filter.list = ["SUM", "MAXIMUM", "MEAN", "MEDIAN", "MINIMUM"]
        param_tech.value = "MEAN"
        param_extent.value = True
        param_nodata.value = True

        params = [param_rasters, param_factor, param_tech, param_extent, param_nodata, param_output]

        return params

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        rasterlist = parameters[0].valueAsText.split(";")
        factor = int(parameters[1].valueAsText)
        tech = parameters[2].valueAsText
        if (parameters[3].valueAsText == 'true'):
            extent = "EXPAND"
        else:
            extent = "TRUNCATE"
        if (parameters[4].valueAsText == 'true'):
            nodata = "DATA"
        else:
            nodata = "NODATA"
        output_dir = parameters[5].valueAsText

        execute_BatchAggregate(rasterlist, factor, tech, extent, nodata, output_dir, messages)

        return
