from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterRasterLayer,
    QgsProcessingOutputString,
    QgsProcessing,
)
from osgeo import gdal


# =============================================================================
# QgsProcessingAlgorithm
# =============================================================================

class VerifyRasterAlignment(QgsProcessingAlgorithm):

    RASTERS = "RASTERS"

    def name(self):
        return "verifyrasteralignment"

    def displayName(self):
        return "Verify raster alignment"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Modeling"

    def groupId(self):
        return "concordiariverlab_floodtools_modeling"

    def createInstance(self):
        return VerifyRasterAlignment()

    def shortHelpString(self):
        return (
            "Verify raster alignment\n\n"
            "Checks that all input rasters share the same origin, pixel size, "
            "and dimensions. Reports mismatches in the log.\n\n"
            "Inputs:\n"
            "- Rasters: two or more raster layers to compare\n\n"
            "Output:\n"
            "- Alignment report printed to the log\n"
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterMultipleLayers(
            self.RASTERS, "Rasters to check",
            layerType=QgsProcessing.TypeRaster,
        ))

    def processAlgorithm(self, parameters, context, feedback):
        layers = self.parameterAsLayerList(parameters, self.RASTERS, context)

        infos = []
        for layer in layers:
            ds = gdal.Open(layer.source())
            gt = ds.GetGeoTransform()
            infos.append({
                "name":    layer.name(),
                "origin_x": gt[0],
                "origin_y": gt[3],
                "pixel_w":  gt[1],
                "pixel_h":  gt[5],
                "cols":     ds.RasterXSize,
                "rows":     ds.RasterYSize,
            })
            ds = None

        # Print summary
        feedback.pushInfo("=== Raster Alignment Report ===")
        for info in infos:
            feedback.pushInfo(
                f"{info['name']}: "
                f"origin=({info['origin_x']}, {info['origin_y']}), "
                f"pixel=({info['pixel_w']}, {info['pixel_h']}), "
                f"size={info['cols']}x{info['rows']}"
            )

        # Check alignment against first raster
        ref = infos[0]
        feedback.pushInfo(f"\nReference: {ref['name']}")
        all_match = True
        for info in infos[1:]:
            mismatches = []
            if round(info['origin_x'], 3) != round(ref['origin_x'], 3) or \
               round(info['origin_y'], 3) != round(ref['origin_y'], 3):
                mismatches.append("origin")
            if info['pixel_w'] != ref['pixel_w'] or info['pixel_h'] != ref['pixel_h']:
                mismatches.append("pixel size")
            if info['cols'] != ref['cols'] or info['rows'] != ref['rows']:
                mismatches.append("dimensions")

            if mismatches:
                feedback.reportError(
                    f"MISMATCH — {info['name']}: {', '.join(mismatches)} differ from reference"
                )
                all_match = False
            else:
                feedback.pushInfo(f"OK — {info['name']}: aligned with reference")

        if all_match:
            feedback.pushInfo("\nAll rasters are aligned.")
        else:
            feedback.reportError("\nAlignment issues detected — see above.")

        return {}