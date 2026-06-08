import math
import numpy as np
from osgeo import gdal, ogr, osr
import tempfile
import os

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterFeatureSink,
    QgsProcessing,
    QgsFeatureSink,
    QgsFeature,
    QgsFields,
    QgsField,
    QgsWkbTypes,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QMetaType

# =============================================================================
# QgsProcessingAlgorithm
# =============================================================================

class ChannelMask(QgsProcessingAlgorithm):

    FROMROUTES    = "FROMROUTES"
    FROMPOLY      = "FROMPOLY"
    D4FD          = "D4FD"
    SNAP_RASTER   = "SNAP_RASTER"
    OUTPUT_RASTER = "OUTPUT_RASTER"
    OUTPUT_POLY   = "OUTPUT_POLY"

    def name(self):
        return "channelmask"

    def displayName(self):
        return "Channel mask"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Modeling"

    def groupId(self):
        return "concordiariverlab_floodtools_modeling"

    def createInstance(self):
        return ChannelMask()

    def shortHelpString(self):
        return (
            "Channel mask\n\n"
            "Creates a channel mask raster and polygon from three input rasters. "
            "Outputs 1 where the channel polygon raster has a value, or where the "
            "D4 flow direction has a value, or where the multi-channel routes raster "
            "has a value. This ensures that the stream network is always comprised "
            "of at least one cell.\n\n"
            "Inputs:\n"
            "- From routes: rasterized multi-channel lines (e.g. fromroutes)\n"
            "- From poly: rasterized channel polygon (e.g. frompoly)\n"
            "- D4 flow direction: D4 flow direction raster (e.g. d4fd)\n"
            "- Snap raster: reference raster for extent and grid alignment (e.g. lidar10m_fd)\n\n"
            "Outputs:\n"
            "- mask_temp: channel mask raster (1 inside channel, NoData outside)\n"
            "- mask_poly: channel mask polygon\n"
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessingParameterRasterLayer,
            QgsProcessingParameterRasterDestination,
            QgsProcessingParameterFeatureSink,
        )

        self.addParameter(QgsProcessingParameterRasterLayer(
            self.FROMROUTES, "From routes (e.g. fromroutes)"))
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.FROMPOLY, "From poly (e.g. frompoly)"))
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.D4FD, "D4 flow direction (e.g. d4fd)"))
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.SNAP_RASTER, "Snap raster for extent and grid alignment (e.g. lidar10m_fd)"))
        self.addParameter(QgsProcessingParameterRasterDestination(
            self.OUTPUT_RASTER, "Channel mask raster (mask_temp)"))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT_POLY, "Channel mask polygon (mask_poly)"))

    def processAlgorithm(self, parameters, context, feedback):
        fromroutes_layer = self.parameterAsRasterLayer(parameters, self.FROMROUTES, context)
        frompoly_layer   = self.parameterAsRasterLayer(parameters, self.FROMPOLY, context)
        d4fd_layer       = self.parameterAsRasterLayer(parameters, self.D4FD, context)
        snap_layer       = self.parameterAsRasterLayer(parameters, self.SNAP_RASTER, context)
        output_raster    = self.parameterAsOutputLayer(parameters, self.OUTPUT_RASTER, context)

        # Build output fields for sink
        out_fields = QgsFields()
        out_fields.append(QgsField("gridcode", QMetaType.Int))

        (sink, sink_id) = self.parameterAsSink(
            parameters, self.OUTPUT_POLY, context,
            out_fields,
            QgsWkbTypes.Polygon,
            fromroutes_layer.crs(),
        )

        execute_channel_mask(
            fromroutes_layer, frompoly_layer, d4fd_layer, snap_layer,
            output_raster, sink, out_fields, feedback
        )

        return {
            self.OUTPUT_RASTER: output_raster,
            self.OUTPUT_POLY: sink_id,
        }


# =============================================================================
# Core logic
# =============================================================================

def execute_channel_mask(fromroutes_layer, frompoly_layer, d4fd_layer, snap_layer,
                         output_raster_path, sink, out_fields, feedback):

    # ------------------------------------------------------------------
    # Load snap raster to get reference extent and geotransform
    # ------------------------------------------------------------------
    snap_ds = gdal.Open(snap_layer.source())
    gt      = snap_ds.GetGeoTransform()
    proj    = snap_ds.GetProjection()
    n_rows  = snap_ds.RasterYSize
    n_cols  = snap_ds.RasterXSize
    snap_ds = None

    # ------------------------------------------------------------------
    # Load rasters and resample to snap grid
    # ------------------------------------------------------------------
    def read_to_snap(layer_source):
        mem_driver = gdal.GetDriverByName('MEM')
        mem_ds = mem_driver.Create('', n_cols, n_rows, 1, gdal.GDT_Float32)
        mem_ds.SetGeoTransform(gt)
        mem_ds.SetProjection(proj)
        mem_ds.GetRasterBand(1).Fill(-9999.0)
        mem_ds.GetRasterBand(1).SetNoDataValue(-9999.0)
        src = gdal.Open(layer_source)
        gdal.ReprojectImage(src, mem_ds, src.GetProjection(), proj,
                            gdal.GRA_NearestNeighbour)
        arr = mem_ds.GetRasterBand(1).ReadAsArray()
        src    = None
        mem_ds = None
        return arr

    feedback.pushInfo("Loading rasters...")
    fr_arr = read_to_snap(fromroutes_layer.source())
    fp_arr = read_to_snap(frompoly_layer.source())
    d4_arr = read_to_snap(d4fd_layer.source())

    # ------------------------------------------------------------------
    # Compute mask: 1 where any of the three rasters has a valid value
    # ------------------------------------------------------------------
    feedback.pushInfo("Computing channel mask...")

    fr_valid = fr_arr != -9999.0
    fp_valid = fp_arr != -9999.0
    d4_valid = d4_arr != -9999.0

    result = (fr_valid | fp_valid | d4_valid).astype(np.float32)
    result[result == 0] = -9999.0

    feedback.pushInfo(f"Valid cells in mask: {int(np.sum(result == 1))}")

    # ------------------------------------------------------------------
    # Write output raster
    # ------------------------------------------------------------------
    driver = gdal.GetDriverByName("GTiff")
    out_ds = driver.Create(output_raster_path, n_cols, n_rows, 1, gdal.GDT_Float32)
    out_ds.SetGeoTransform(gt)
    out_ds.SetProjection(proj)
    out_band = out_ds.GetRasterBand(1)
    out_band.SetNoDataValue(-9999.0)
    out_band.WriteArray(result)
    out_band.FlushCache()
    out_ds = None

    feedback.pushInfo("Mask raster written. Running polygonize...")

    # ------------------------------------------------------------------
    # Polygonize to temp file then read into sink
    # ------------------------------------------------------------------
    src_ds   = gdal.Open(output_raster_path)
    src_band = src_ds.GetRasterBand(1)

    srs = osr.SpatialReference()
    srs.ImportFromWkt(proj)

    # Write to temp GPKG
    tmp_path = tempfile.mktemp(suffix='.gpkg')
    ogr_driver  = ogr.GetDriverByName("GPKG")
    tmp_ogr_ds  = ogr_driver.CreateDataSource(tmp_path)
    tmp_layer   = tmp_ogr_ds.CreateLayer("mask_poly", srs=srs, geom_type=ogr.wkbPolygon)
    field_defn  = ogr.FieldDefn("gridcode", ogr.OFTInteger)
    tmp_layer.CreateField(field_defn)

    gdal.Polygonize(src_band, src_band, tmp_layer, 0, [], callback=None)

    tmp_ogr_ds.FlushCache()
    tmp_ogr_ds = None
    src_ds     = None

    # Read temp file into sink
    tmp_lyr = QgsVectorLayer(tmp_path, "mask_poly_tmp", "ogr")
    for feat in tmp_lyr.getFeatures():
        out_feat = QgsFeature(out_fields)
        out_feat.setGeometry(feat.geometry())
        out_feat["gridcode"] = feat["gridcode"]
        sink.addFeature(out_feat, QgsFeatureSink.FastInsert)

    # Clean up temp file
    try:
        os.remove(tmp_path)
    except Exception:
        pass

    feedback.pushInfo("Channel mask complete.")