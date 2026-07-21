import os
from osgeo import gdal
from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterFeatureSink,
    QgsFields,
    QgsField,
    QgsFeature,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QVariant


class CheckInbciOnD4(QgsProcessingAlgorithm):

    INBCI      = "INBCI"
    D4FD       = "D4FD"
    OUTPUT     = "OUTPUT"

    def name(self):
        return "checkinbcionD4"

    def displayName(self):
        return "Check inbci points on D4 path"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Modeling"

    def groupId(self):
        return "concordiariverlab_floodtools_modeling"

    def createInstance(self):
        return CheckInbciOnD4()

    def shortHelpString(self):
        return (
            "Check inbci points fall on the D4 flow direction path\n\n"
            "Samples the D4 flow direction raster at each inbci point and adds an "
            "on_d4 boolean field: True if the point lands on a valid D4 cell, False "
            "if it lands on nodata or outside the raster. Points flagged False "
            "should be manually moved onto the D4 network before proceeding to "
            "flood discharge assignment.\n\n"
            "Inputs:\n"
            "- inbci: point layer from HydraulicSimPrep (Tiles\\inbci.gpkg)\n"
            "- D4 flow direction: watershed-scale D4 raster (e.g. Lisflood_inputs\\d4fd)\n\n"
            "Output: copy of inbci with an added on_d4 boolean field.\n"
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.INBCI, "inbci points",
        ))
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.D4FD, "D4 flow direction (d4fd)",
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, "inbci with on_d4 flag",
        ))

    def processAlgorithm(self, parameters, context, feedback):
        inbci = self.parameterAsVectorLayer(parameters, self.INBCI, context)
        d4fd  = self.parameterAsRasterLayer(parameters, self.D4FD, context)

        if inbci is None:
            raise QgsProcessingException("inbci layer is invalid")
        if d4fd is None:
            raise QgsProcessingException("D4 flow direction raster is invalid")

        out_fields = QgsFields(inbci.fields())
        out_fields.append(QgsField("on_d4", QVariant.Bool))

        sink, dest_id = self.parameterAsSink(
            parameters, self.OUTPUT, context,
            out_fields, inbci.wkbType(), inbci.sourceCrs(),
        )
        if sink is None:
            raise QgsProcessingException("Could not create output sink")

        ds = gdal.Open(d4fd.source())
        if ds is None:
            raise QgsProcessingException(f"Could not open D4 raster: {d4fd.source()}")
        gt = ds.GetGeoTransform()
        band = ds.GetRasterBand(1)
        nodata = band.GetNoDataValue()

        off_network = []
        n_checked = 0

        for feat in inbci.getFeatures():
            if feedback.isCanceled():
                break
            n_checked += 1
            pt = feat.geometry().asPoint()
            col = int((pt.x() - gt[0]) / gt[1])
            row = int((pt.y() - gt[3]) / gt[5])

            on_d4 = False
            if 0 <= col < ds.RasterXSize and 0 <= row < ds.RasterYSize:
                val = band.ReadAsArray(col, row, 1, 1)
                if val is not None:
                    d4_val = float(val[0][0])
                    if nodata is None or d4_val != nodata:
                        on_d4 = True

            if not on_d4:
                off_network.append((feat.id(), pt.x(), pt.y()))

            out_feat = QgsFeature(out_fields)
            out_feat.setGeometry(feat.geometry())
            attrs = feat.attributes()
            attrs.append(on_d4)
            out_feat.setAttributes(attrs)
            sink.addFeature(out_feat)

        ds = None

        feedback.pushInfo(f"Checked {n_checked} point(s).")
        if off_network:
            feedback.pushWarning(
                f"{len(off_network)} point(s) NOT on D4 path — manually move these "
                f"onto the D4 network before assigning flood discharges:"
            )
            for fid, x, y in off_network:
                feedback.pushWarning(f"  fid={fid} ({x:.1f},{y:.1f})")
        else:
            feedback.pushInfo("All inbci points fall on the D4 path.")

        return {self.OUTPUT: dest_id}