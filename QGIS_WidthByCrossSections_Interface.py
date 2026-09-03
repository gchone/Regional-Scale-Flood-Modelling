from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))

import QGIStools
from QGIS_Messages import Messages
from WidthByCrossSections import execute_WidthByCrossSections

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessing,
)


class QGIS_WidthByCrossSections(QgsProcessingAlgorithm):
    STREAMNETWORK = "STREAMNETWORK"
    IDFIELD = "IDFIELD"
    RIVERBED = "RIVERBED"
    INEFFAREA = "INEFFAREA"
    MAXWIDTH = "MAXWIDTH"
    SPACING = "SPACING"
    TRANSECTS = "TRANSECTS"
    CSPOINTS = "CSPOINTS"

    def name(self):
        return "width_by_cross_sections"

    def displayName(self):
        return "Width by cross-sections"

    def group(self):
        return "Large Scale Flood Modelling Toolbox"

    def groupId(self):
        return "large_scale_flood_modelling_toolbox"

    def createInstance(self):
        return QGIS_WidthByCrossSections()

    def shortHelpString(self):
        return (
            "Measure river width by building regularly spaced cross-sections along a routed stream "
            "network, trimming them to the river polygon, removing problematic crossings, and "
            "writing both the final transects and the surviving width points."
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessingParameterVectorLayer,
            QgsProcessingParameterField,
            QgsProcessingParameterNumber,
            QgsProcessingParameterFeatureSink,
        )

        self.addParameter(QgsProcessingParameterVectorLayer(self.STREAMNETWORK, "Route layer (or lines)", [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterField(self.IDFIELD, "RouteID field", parentLayerParameterName=self.STREAMNETWORK, defaultValue="RID"))
        self.addParameter(QgsProcessingParameterVectorLayer(self.RIVERBED, "River polygons", [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterVectorLayer(self.INEFFAREA, "Polygons identifying dead water", [QgsProcessing.TypeVectorPolygon], optional=True))
        self.addParameter(QgsProcessingParameterNumber(self.MAXWIDTH, "Maximum width of cross-sections(m)", type=QgsProcessingParameterNumber.Double, defaultValue=1000.0, minValue=0.0))
        self.addParameter(QgsProcessingParameterNumber(self.SPACING, "Interval between cross-sections (m)", type=QgsProcessingParameterNumber.Double, defaultValue=5.0, minValue=0.0))
        self.addParameter(QgsProcessingParameterFeatureSink(self.TRANSECTS, "Output: Cross-sections"))
        self.addParameter(QgsProcessingParameterFeatureSink(self.CSPOINTS, "Output: Points at cross-section"))

    def processAlgorithm(self, parameters, context, feedback):
        streamnetwork = self.parameterAsVectorLayer(parameters, self.STREAMNETWORK, context)
        idfield = self.parameterAsString(parameters, self.IDFIELD, context)
        riverbed = self.parameterAsVectorLayer(parameters, self.RIVERBED, context)
        ineffarea = self.parameterAsVectorLayer(parameters, self.INEFFAREA, context)
        maxwidth = self.parameterAsDouble(parameters, self.MAXWIDTH, context)
        spacing = self.parameterAsDouble(parameters, self.SPACING, context)
        transects = self.parameterAsOutputLayer(parameters, self.TRANSECTS, context)
        cspoints = self.parameterAsOutputLayer(parameters, self.CSPOINTS, context)

        if None in [streamnetwork, riverbed]:
            raise QgsProcessingException("One or more required input layers are invalid")

        execute_WidthByCrossSections(
            streamnetwork,
            idfield,
            riverbed,
            ineffarea,
            maxwidth,
            spacing,
            transects,
            cspoints,
            GIStools=QGIStools,
            messages=Messages(feedback),
        )
        return {
            self.TRANSECTS: transects,
            self.CSPOINTS: cspoints,
        }


WidthByCrossSections = QGIS_WidthByCrossSections
