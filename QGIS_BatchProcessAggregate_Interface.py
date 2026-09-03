from pathlib import Path
import os
import sys

sys.path.append(str(Path(__file__).resolve().parent))

from BatchProcessAggregate import execute_BatchProcessAggregate
import QGIStools
from QGIS_Messages import Messages

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessing,
)


class QGIS_BatchProcessAggregate(QgsProcessingAlgorithm):
    INPUT_RASTERS = "INPUT_RASTERS"
    FACTOR = "FACTOR"
    TECH = "TECH"
    EXTENT = "EXTENT"
    IGNORE_NODATA = "IGNORE_NODATA"
    OUT_DIR = "OUT_DIR"

    TECH_OPTIONS = ["SUM", "MAXIMUM", "MEAN", "MEDIAN", "MINIMUM"]

    def name(self):
        return "batch_process_aggregate"

    def displayName(self):
        return "Batch process aggregate"

    def group(self):
        return "Large Scale Flood Modelling Toolbox"

    def groupId(self):
        return "large_scale_flood_modelling_toolbox"

    def createInstance(self):
        return QGIS_BatchProcessAggregate()

    def shortHelpString(self):
        return (
            "Batch process aggregate\n\n"
            "Applies the ArcGIS Aggregate behavior to multiple rasters, including "
            "SUM/MAXIMUM/MEAN/MEDIAN/MINIMUM statistics, optional extent expansion, "
            "ArcGIS-style NoData handling, and snap alignment to the first aggregated output."
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessingParameterMultipleLayers,
            QgsProcessingParameterNumber,
            QgsProcessingParameterEnum,
            QgsProcessingParameterBoolean,
            QgsProcessingParameterFolderDestination,
        )

        self.addParameter(QgsProcessingParameterMultipleLayers(
            self.INPUT_RASTERS,
            "Rasters to aggregate",
            layerType=QgsProcessing.TypeRaster,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.FACTOR,
            "Cell factor",
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=10,
            minValue=1,
        ))
        self.addParameter(QgsProcessingParameterEnum(
            self.TECH,
            "Aggregation technique",
            options=self.TECH_OPTIONS,
            defaultValue=2,
        ))
        self.addParameter(QgsProcessingParameterBoolean(
            self.EXTENT,
            "Expand extent if needed",
            defaultValue=True,
        ))
        self.addParameter(QgsProcessingParameterBoolean(
            self.IGNORE_NODATA,
            "Ignore NoData in calculations",
            defaultValue=True,
        ))
        self.addParameter(QgsProcessingParameterFolderDestination(
            self.OUT_DIR,
            "Output location",
        ))

    def processAlgorithm(self, parameters, context, feedback):
        rasters = self.parameterAsLayerList(parameters, self.INPUT_RASTERS, context)
        factor = self.parameterAsInt(parameters, self.FACTOR, context)
        tech_index = self.parameterAsEnum(parameters, self.TECH, context)
        expand_extent = self.parameterAsBool(parameters, self.EXTENT, context)
        ignore_nodata = self.parameterAsBool(parameters, self.IGNORE_NODATA, context)
        out_dir = self.parameterAsString(parameters, self.OUT_DIR, context)

        if not rasters:
            raise QgsProcessingException("No rasters provided")
        if not out_dir:
            raise QgsProcessingException("Output location is invalid")

        os.makedirs(out_dir, exist_ok=True)
        execute_BatchProcessAggregate(
            rasters,
            factor,
            self.TECH_OPTIONS[tech_index],
            "EXPAND" if expand_extent else "TRUNCATE",
            "DATA" if ignore_nodata else "NODATA",
            out_dir,
            GIStools=QGIStools,
            messages=Messages(feedback),
        )
        return {self.OUT_DIR: out_dir}


BatchProcessAggregate = QGIS_BatchProcessAggregate
