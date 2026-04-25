import os
import numpy as np
from osgeo import gdal, ogr, osr
from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessing,
)
import processing


class BridgeCorrection(QgsProcessingAlgorithm):

    DEM = "DEM"
    BRIDGES = "BRIDGES"
    NODATA = "NODATA"
    OUTPUT = "OUTPUT"

    def name(self):
        return "bridgecorrection"

    def displayName(self):
        return "Bridges and culverts correction"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Modeling"

    def groupId(self):
        return "concordiariverlab_floodtools_modeling"

    def createInstance(self):
        return BridgeCorrection()

    def shortHelpString(self):
        return (
            "Bridges and culverts correction\n\n"
            "Corrects bridge and culvert pixels in a DEM by replacing them with "
            "hydrologically filled interpolated values. Bridge polygon interiors and "
            "boundaries are rasterized (ALL_TOUCHED), set to NoData, then a hydrological "
            "fill (GRASS r.fill.dir) is run over the full DEM. The filled values are pasted "
            "back only where bridges were, leaving the rest of the DEM unchanged.\n\n"
            "Inputs:\n"
            "- DEM: input raster (e.g., lidar3m_min)\n"
            "- Bridges to be corrected: polygon layer of bridge/culvert footprints\n"
            "- NoData value: value used for NoData in input and output raster (default: -9999)\n\n"
            "Output:\n"
            "- Corrected DEM (e.g., lidar3m_forws)\n"
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessingParameterRasterLayer,
            QgsProcessingParameterFeatureSource,
            QgsProcessingParameterNumber,
            QgsProcessingParameterRasterDestination,
        )

        self.addParameter(QgsProcessingParameterRasterLayer(
            self.DEM, "DEM (lidar3m_min"
        ))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.BRIDGES, "Bridges to be corrected (geometry.gpkg/bridges)",
            [QgsProcessing.TypeVectorPolygon]
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.NODATA, "NoData value",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=-9999.0
        ))
        self.addParameter(QgsProcessingParameterRasterDestination(
            self.OUTPUT, "Result - Corrected DEM (lidar3m_forws)"
        ))

    def processAlgorithm(self, parameters, context, feedback):
        from qgis.core import (
            QgsProcessingParameterNumber,
        )

        dem_layer = self.parameterAsRasterLayer(parameters, self.DEM, context)
        bridges_source = self.parameterAsSource(parameters, self.BRIDGES, context)
        nodata_val = self.parameterAsDouble(parameters, self.NODATA, context)
        output_path = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)

        if dem_layer is None:
            raise QgsProcessingException("Input DEM layer is invalid")
        if bridges_source is None:
            raise QgsProcessingException("Input bridges layer is invalid")

        result = execute_bridge_correction(
            dem_layer, bridges_source, nodata_val, output_path, feedback
        )
        return {self.OUTPUT: result}

# =============================================================================
# Helpers
# =============================================================================

def _rasterize_bridges(bridges_source, gt, proj, cols, rows):
    """
    Rasterizes bridge polygons into a boolean mask.
    ALL_TOUCHED=TRUE ensures boundary pixels are included (mirrors ArcGIS v1.1 behaviour).

    Returns
    -------
    np.ndarray of bool, shape (rows, cols)
    """
    mem_driver = ogr.GetDriverByName("Memory")
    mem_ds = mem_driver.CreateDataSource("memdata")
    srs = osr.SpatialReference()
    srs.ImportFromWkt(proj)
    mem_layer = mem_ds.CreateLayer("bridges", srs=srs, geom_type=ogr.wkbPolygon)

    for feat in bridges_source.getFeatures():
        ogr_geom = ogr.CreateGeometryFromWkt(feat.geometry().asWkt())
        ogr_feat = ogr.Feature(mem_layer.GetLayerDefn())
        ogr_feat.SetGeometry(ogr_geom)
        mem_layer.CreateFeature(ogr_feat)

    mem_rast_driver = gdal.GetDriverByName("MEM")
    mask_ds = mem_rast_driver.Create("", cols, rows, 1, gdal.GDT_Byte)
    mask_ds.SetGeoTransform(gt)
    mask_ds.SetProjection(proj)
    mask_ds.GetRasterBand(1).Fill(0)
    mask_ds.GetRasterBand(1).SetNoDataValue(255)

    gdal.RasterizeLayer(mask_ds, [1], mem_layer, burn_values=[1],
                        options=["ALL_TOUCHED=TRUE"])
    mask_array = mask_ds.GetRasterBand(1).ReadAsArray().astype(bool)
    mask_ds = None
    mem_ds = None

    return mask_array


def _write_raster(array, gt, proj, nodata_val, output_path):
    """Writes a float32 numpy array to a GeoTIFF."""
    driver = gdal.GetDriverByName("GTiff")
    rows, cols = array.shape
    out_ds = driver.Create(output_path, cols, rows, 1, gdal.GDT_Float32)
    out_ds.SetGeoTransform(gt)
    out_ds.SetProjection(proj)
    band = out_ds.GetRasterBand(1)
    band.SetNoDataValue(nodata_val)
    band.WriteArray(array)
    out_ds.FlushCache()
    out_ds = None

# =============================================================================
# Core logic
# =============================================================================

def execute_bridge_correction(dem_layer, bridges_source, nodata_val, output_path, feedback):
    """
    Corrects bridge and culvert pixels in a DEM by replacing them with
    hydrologically filled interpolated values.

    Parameters
    ----------
    dem_layer       : QgsRasterLayer
    bridges_source  : QgsFeatureSource - bridge polygons
    nodata_val      : float
    output_path     : str
    feedback        : QgsProcessingFeedback

    Returns
    -------
    output_path : str
    """
    dem_path = dem_layer.source()
    ds = gdal.Open(dem_path)
    gt = ds.GetGeoTransform()
    proj = ds.GetProjection()
    cols = ds.RasterXSize
    rows = ds.RasterYSize
    dem_array = ds.GetRasterBand(1).ReadAsArray().astype(np.float32)
    ds = None

    feedback.pushInfo("Rasterizing bridge polygons...")
    bridge_mask = _rasterize_bridges(bridges_source, gt, proj, cols, rows)

    feedback.pushInfo(f"Bridge mask True count: {bridge_mask.sum()}")

    # Step 1: For each bridge zone, find the minimum valid elevation
    # fill bridge pixels with that value
    feedback.pushInfo("Computing zonal minimum per bridge zone...")
    dem_with_bridge_fill = dem_array.copy()

    for feat in bridges_source.getFeatures():
        geom = feat.geometry()
        ogr_geom = ogr.CreateGeometryFromWkt(geom.asWkt())

        # Rasterize this single bridge polygon
        mem_driver = ogr.GetDriverByName("Memory")
        mem_ds = mem_driver.CreateDataSource("memdata")
        srs = osr.SpatialReference()
        srs.ImportFromWkt(proj)
        mem_layer = mem_ds.CreateLayer("bridge", srs=srs, geom_type=ogr.wkbPolygon)
        ogr_feat = ogr.Feature(mem_layer.GetLayerDefn())
        ogr_feat.SetGeometry(ogr_geom)
        mem_layer.CreateFeature(ogr_feat)

        mem_rast = gdal.GetDriverByName("MEM").Create("", cols, rows, 1, gdal.GDT_Byte)
        mem_rast.SetGeoTransform(gt)
        mem_rast.SetProjection(proj)
        mem_rast.GetRasterBand(1).Fill(0)
        gdal.RasterizeLayer(mem_rast, [1], mem_layer,
                            burn_values=[1], options=["ALL_TOUCHED=TRUE"])
        single_mask = mem_rast.GetRasterBand(1).ReadAsArray().astype(bool)
        mem_rast = None
        mem_ds = None

        # Get minimum valid elevation within this bridge zone
        bridge_pixels = dem_array[single_mask]
        valid_pixels = bridge_pixels[bridge_pixels != nodata_val]

        if len(valid_pixels) == 0:
            feedback.pushWarning(f"  Bridge feature {feat.id()} has no valid DEM pixels — skipping")
            continue

        zone_min = float(np.min(valid_pixels))
        feedback.pushInfo(f"  Bridge {feat.id()}: {single_mask.sum()} pixels, min elevation = {zone_min:.2f}m")

        # Fill bridge pixels with the zone minimum
        dem_with_bridge_fill[single_mask] = zone_min

    # Step 2: Paste zonal minimum values back only at bridge pixels
    feedback.pushInfo("Applying zonal minimum values to bridge pixels...")
    result_array = np.where(bridge_mask, dem_with_bridge_fill, dem_array)

    feedback.pushInfo(f"Writing result to {output_path}...")
    _write_raster(result_array, gt, proj, nodata_val, output_path)

    feedback.pushInfo("Bridge correction complete.")
    return output_path