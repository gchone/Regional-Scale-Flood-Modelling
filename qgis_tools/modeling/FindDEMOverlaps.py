import os
import numpy as np

from osgeo import gdal, ogr, osr
from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsFeatureSink,
    QgsFeature,
    QgsFields,
    QgsField,
    QgsGeometry,
    QgsCoordinateReferenceSystem,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QMetaType


class FindDEMOverlaps(QgsProcessingAlgorithm):

    DEM_FOLDER         = "DEM_FOLDER"
    DEM_FOOTPRINTS_RAW = "DEM_FOOTPRINTS_RAW"
    DEM_OVERLAPS       = "DEM_OVERLAPS"

    def name(self):
        return "find_dem_overlaps"

    def displayName(self):
        return "Find DEM overlaps"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Modeling"

    def groupId(self):
        return "concordiariverlab_floodtools_modeling"

    def createInstance(self):
        return FindDEMOverlaps()

    def shortHelpString(self):
        return (
            "Find DEM overlaps\n\n"
            "Scans a folder of GeoTIFF rasters, creates an actual data footprint "
            "polygon for each DEM (excluding NoData pixels), then identifies all "
            "pairwise overlaps between footprints.\n\n"
            "Inputs:\n"
            "- DEM folder: folder containing .tif raster files\n\n"
            "Outputs:\n"
            "- DEM_footprints_raw: one polygon per DEM with ID_DEM field (filename)\n"
            "- DEM_overlaps: one polygon per pairwise overlap with ID_DEM_1 and "
            "ID_DEM_2 fields identifying the two overlapping DEMs\n\n"
            "Workflow:\n"
            "1. Run this tool to identify overlapping DEM pairs\n"
            "2. Inspect DEM_footprints_raw and DEM_overlaps to decide where to clip\n"
            "3. Manually clip the DEMs following the documentation guidelines\n"
            "4. Run Create DEM footprints on the clipped DEM folder\n"
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessingParameterFile,
            QgsProcessingParameterFeatureSink,
        )

        self.addParameter(QgsProcessingParameterFile(
            self.DEM_FOLDER,
            "DEM folder",
            behavior=QgsProcessingParameterFile.Folder,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.DEM_FOOTPRINTS_RAW,
            "DEM_footprints_raw",
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.DEM_OVERLAPS,
            "DEM_overlaps",
        ))

    # =============================================================================
    # Core logic
    # =============================================================================

    def processAlgorithm(self, parameters, context, feedback):
        from qgis.core import (
            QgsProcessingParameterFile,
            QgsProcessingParameterFeatureSink,
        )

        dem_folder = self.parameterAsString(parameters, self.DEM_FOLDER, context)

        if not os.path.isdir(dem_folder):
            raise QgsProcessingException(f"DEM folder not found: {dem_folder}")

        tif_files = sorted([
            f for f in os.listdir(dem_folder)
            if f.lower().endswith(".tif")
        ])

        if not tif_files:
            raise QgsProcessingException("No .tif files found in the DEM folder")

        feedback.pushInfo(f"Found {len(tif_files)} .tif file(s) in {dem_folder}")

        # --- Build footprints ---
        footprints = []  # list of (filename, QgsGeometry)
        crs = QgsCoordinateReferenceSystem()
        total = len(tif_files)

        for i, filename in enumerate(tif_files):
            if feedback.isCanceled():
                break

            feedback.setProgress(int(40 * i / max(1, total)))
            feedback.pushInfo(f"Computing footprint {i + 1}/{total}: {filename}")

            filepath = os.path.join(dem_folder, filename)
            geom = _get_raster_footprint(filepath, feedback)

            if geom is None:
                continue

            if not crs.isValid():
                ds = gdal.Open(filepath)
                if ds:
                    crs.createFromWkt(ds.GetProjection())
                    ds = None

            footprints.append((filename, geom))

        # --- Write footprint features ---
        fp_fields = QgsFields()
        fp_fields.append(QgsField("ID_DEM", QMetaType.QString))

        (fp_sink, fp_id) = self.parameterAsSink(
            parameters, self.DEM_FOOTPRINTS_RAW, context,
            fp_fields,
            QgsWkbTypes.Polygon,
            crs,
        )

        for filename, geom in footprints:
            if feedback.isCanceled():
                break
            f = QgsFeature(fp_fields)
            f.setGeometry(geom)
            f.setAttribute("ID_DEM", filename)
            fp_sink.addFeature(f, QgsFeatureSink.FastInsert)

        # --- Find pairwise overlaps ---
        ov_fields = QgsFields()
        ov_fields.append(QgsField("ID_DEM_1", QMetaType.QString))
        ov_fields.append(QgsField("ID_DEM_2", QMetaType.QString))

        (ov_sink, ov_id) = self.parameterAsSink(
            parameters, self.DEM_OVERLAPS, context,
            ov_fields,
            QgsWkbTypes.Polygon,
            crs,
        )

        n = len(footprints)
        pair_count = 0
        overlap_count = 0

        for i in range(n):
            if feedback.isCanceled():
                break
            for j in range(i + 1, n):
                if feedback.isCanceled():
                    break

                id_1, geom_1 = footprints[i]
                id_2, geom_2 = footprints[j]
                pair_count += 1

                if not geom_1.intersects(geom_2):
                    continue

                intersection = geom_1.intersection(geom_2)
                if intersection is None or intersection.isEmpty():
                    continue

                # Only keep polygon geometry (ignore point/line touches)
                if intersection.type() != QgsWkbTypes.PolygonGeometry:
                    continue

                feedback.pushInfo(f"  Overlap found: {id_1} ∩ {id_2}")
                overlap_count += 1

                f = QgsFeature(ov_fields)
                f.setGeometry(intersection)
                f.setAttribute("ID_DEM_1", id_1)
                f.setAttribute("ID_DEM_2", id_2)
                ov_sink.addFeature(f, QgsFeatureSink.FastInsert)

            feedback.setProgress(40 + int(60 * i / max(1, n)))

        feedback.pushInfo(
            f"Done. {len(footprints)} footprint(s), "
            f"{overlap_count} pairwise overlap(s) found across {pair_count} pair(s) checked."
        )

        if overlap_count == 0:
            feedback.pushInfo(
                "No overlaps found — you can proceed directly to Create DEM footprints."
            )

        return {
            self.DEM_FOOTPRINTS_RAW: fp_id,
            self.DEM_OVERLAPS: ov_id,
        }


# =============================================================================
# Helpers
# =============================================================================

def _get_raster_footprint(filepath, feedback=None):
    """
    Derives the actual data footprint of a raster by masking NoData pixels
    and polygonizing the valid data mask using GDAL.

    Args:
        filepath : str — path to .tif raster
        feedback : QgsProcessingFeedback or None

    Returns:
        QgsGeometry (Polygon or MultiPolygon) of the valid data extent,
        or None if the raster could not be read or has no valid data.
    """
    ds = gdal.Open(filepath)
    if ds is None:
        if feedback:
            feedback.pushWarning(f"Could not open {os.path.basename(filepath)}")
        return None

    gt     = ds.GetGeoTransform()
    proj   = ds.GetProjection()
    band   = ds.GetRasterBand(1)
    nodata = band.GetNoDataValue()
    arr    = band.ReadAsArray().astype(np.float32)
    ds     = None

    # Build valid-data mask (1 = valid, 0 = NoData)
    if nodata is not None:
        mask = np.where(arr == nodata, 0, 1).astype(np.uint8)
    else:
        mask = np.ones_like(arr, dtype=np.uint8)

    if mask.sum() == 0:
        if feedback:
            feedback.pushWarning(
                f"{os.path.basename(filepath)} has no valid data pixels"
            )
        return None

    # Write mask to in-memory raster
    mem_driver = gdal.GetDriverByName("MEM")
    mask_ds    = mem_driver.Create("", mask.shape[1], mask.shape[0], 1, gdal.GDT_Byte)
    mask_ds.SetGeoTransform(gt)
    mask_ds.SetProjection(proj)
    mask_band = mask_ds.GetRasterBand(1)
    mask_band.WriteArray(mask)
    mask_band.SetNoDataValue(0)

    # Polygonize valid data mask into an in-memory OGR layer
    mem_ogr    = ogr.GetDriverByName("Memory")
    mem_ogr_ds = mem_ogr.CreateDataSource("memdata")
    srs        = osr.SpatialReference()
    srs.ImportFromWkt(proj)
    ogr_layer  = mem_ogr_ds.CreateLayer("footprint", srs=srs, geom_type=ogr.wkbPolygon)
    fd         = ogr.FieldDefn("val", ogr.OFTInteger)
    ogr_layer.CreateField(fd)

    gdal.Polygonize(mask_band, mask_band, ogr_layer, 0, [], callback=None)
    mask_ds = None

    # Collect and dissolve all polygons where value == 1 (valid data)
    union_geom = None
    for ogr_feat in ogr_layer:
        if ogr_feat.GetField("val") != 1:
            continue
        wkt  = ogr_feat.GetGeometryRef().ExportToWkt()
        geom = QgsGeometry.fromWkt(wkt)
        if union_geom is None:
            union_geom = geom
        else:
            union_geom = union_geom.combine(geom)

    mem_ogr_ds = None
    return union_geom