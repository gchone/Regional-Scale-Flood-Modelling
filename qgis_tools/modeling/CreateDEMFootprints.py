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


class CreateDEMFootprints(QgsProcessingAlgorithm):

    DEM_FOLDER     = "DEM_FOLDER"
    DEM_FOOTPRINTS = "DEM_FOOTPRINTS"

    def name(self):
        return "create_dem_footprints"

    def displayName(self):
        return "Create DEM footprints"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Modeling"

    def groupId(self):
        return "concordiariverlab_floodtools_modeling"

    def createInstance(self):
        return CreateDEMFootprints()

    def shortHelpString(self):
        return (
            "Create DEM footprints\n\n"
            "Scans a folder of manually clipped GeoTIFF rasters and creates a "
            "footprint polygon layer based on actual data extent (excluding NoData "
            "pixels). Warns if any overlaps or gaps are detected between footprints.\n\n"
            "Run Find DEM overlaps first to identify overlapping pairs, then "
            "manually clip the DEMs following the documentation guidelines before "
            "running this tool.\n\n"
            "Inputs:\n"
            "- DEM folder: folder containing manually clipped .tif raster files\n\n"
            "Outputs:\n"
            "- DEM_footprints: polygon layer with ID_DEM field (filename)\n\n"
            "Warnings are raised if:\n"
            "- Any two footprints still overlap\n"
            "- Any gaps exist between adjacent footprints\n"
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessingParameterFile,
            QgsProcessingParameterFeatureSink,
        )

        self.addParameter(QgsProcessingParameterFile(
            self.DEM_FOLDER,
            "DEM folder (manually clipped rasters)",
            behavior=QgsProcessingParameterFile.Folder,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.DEM_FOOTPRINTS,
            "DEM_footprints",
        ))

    def processAlgorithm(self, parameters, context, feedback):
        dem_folder = self.parameterAsString(parameters, self.DEM_FOLDER, context)

        if not os.path.isdir(dem_folder):
            raise QgsProcessingException(f"DEM folder not found: {dem_folder}")

        footprint_features, crs = create_dem_footprints(
            dem_folder=dem_folder,
            feedback=feedback,
        )

        if not footprint_features:
            raise QgsProcessingException("No .tif files found in the DEM folder")

        out_fields = QgsFields()
        out_fields.append(QgsField("ID_DEM", QMetaType.QString))

        (fp_sink, fp_id) = self.parameterAsSink(
            parameters, self.DEM_FOOTPRINTS, context,
            out_fields,
            QgsWkbTypes.Polygon,
            crs,
        )
        for geom, id_dem in footprint_features:
            if feedback.isCanceled():
                break
            f = QgsFeature(out_fields)
            f.setGeometry(geom)
            f.setAttribute("ID_DEM", id_dem)
            fp_sink.addFeature(f, QgsFeatureSink.FastInsert)

        return {self.DEM_FOOTPRINTS: fp_id}


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

    gt      = ds.GetGeoTransform()
    proj    = ds.GetProjection()
    band    = ds.GetRasterBand(1)
    nodata  = band.GetNoDataValue()
    arr     = band.ReadAsArray().astype(np.float32)
    ds      = None

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


# =============================================================================
# Core logic
# =============================================================================

def create_dem_footprints(dem_folder, feedback=None):
    """
    Scans a folder of manually clipped .tif files, creates actual data
    footprints using GDAL Polygonize, checks for remaining overlaps and
    gaps, and returns the footprint features.

    Args:
        dem_folder : str — path to folder containing clipped .tif files
        feedback   : QgsProcessingFeedback or None

    Returns:
        footprint_features : list of (QgsGeometry, id_dem)
        crs                : QgsCoordinateReferenceSystem
    """
    tif_files = sorted([
        f for f in os.listdir(dem_folder)
        if f.lower().endswith(".tif")
    ])

    if feedback:
        feedback.pushInfo(f"Found {len(tif_files)} .tif file(s) in {dem_folder}")

    # ------------------------------------------------------------------
    # Step 1: Build footprint for each DEM
    # ------------------------------------------------------------------
    footprints = []  # list of (id_dem, QgsGeometry)
    crs        = QgsCoordinateReferenceSystem()
    total      = len(tif_files)

    for i, filename in enumerate(tif_files):
        if feedback and feedback.isCanceled():
            break
        if feedback:
            feedback.setProgress(int(50 * i / max(1, total)))
            feedback.pushInfo(f"  Computing footprint for {filename}...")

        filepath = os.path.join(dem_folder, filename)
        geom     = _get_raster_footprint(filepath, feedback)

        if geom is None:
            continue

        if not crs.isValid():
            ds = gdal.Open(filepath)
            if ds:
                crs.createFromWkt(ds.GetProjection())
                ds = None

        footprints.append((filename, geom))

    # ------------------------------------------------------------------
    # Step 2: Check for remaining overlaps
    # ------------------------------------------------------------------
    if feedback:
        feedback.pushInfo("Checking for remaining overlaps...")

    n             = len(footprints)
    overlap_count = 0

    for i in range(n):
        for j in range(i + 1, n):
            id_a, geom_a = footprints[i]
            id_b, geom_b = footprints[j]
            if geom_a.intersects(geom_b):
                intersection = geom_a.intersection(geom_b)
                if (
                    intersection is not None
                    and not intersection.isEmpty()
                    and intersection.type() == QgsWkbTypes.PolygonGeometry
                ):
                    overlap_count += 1
                    if feedback:
                        feedback.pushWarning(
                            f"  Overlap detected between '{id_a}' and '{id_b}' — "
                            f"consider re-clipping"
                        )

    if overlap_count == 0 and feedback:
        feedback.pushInfo("  No overlaps found. ✓")

    # ------------------------------------------------------------------
    # Step 3: Check for gaps between footprints
    # ------------------------------------------------------------------
    if feedback:
        feedback.pushInfo("Checking for gaps between footprints...")

    gap_count = 0
    if footprints:
        union_geom = footprints[0][1]
        for _, geom in footprints[1:]:
            union_geom = union_geom.combine(geom)

        if union_geom.isMultipart():
            parts = union_geom.asMultiPolygon()
            for part in parts:
                if len(part) > 1:
                    gap_count += len(part) - 1
                    if feedback:
                        feedback.pushWarning(
                            f"  Gap detected in union geometry — "
                            f"there may be uncovered areas between DEMs"
                        )
        else:
            rings = union_geom.asPolygon()
            if len(rings) > 1:
                gap_count += len(rings) - 1
                if feedback:
                    feedback.pushWarning(
                        f"  {len(rings) - 1} interior ring(s) detected in union — "
                        f"there may be gaps between DEMs"
                    )

    if gap_count == 0 and feedback:
        feedback.pushInfo("  No gaps found. ✓")

    footprint_features = [(geom, id_dem) for id_dem, geom in footprints]

    if feedback:
        feedback.pushInfo(
            f"Done. {len(footprint_features)} footprint(s) created. "
            f"{overlap_count} overlap(s), {gap_count} gap(s) detected."
        )

    return footprint_features, crs