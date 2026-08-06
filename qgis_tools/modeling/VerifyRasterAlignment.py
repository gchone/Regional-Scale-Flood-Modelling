from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterMultipleLayers,
    QgsProcessing,
)
from osgeo import gdal


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
            "Checks that all input rasters share the same pixel size and grid "
            "phase (i.e. cell edges line up) relative to the first raster "
            "selected, which is treated as the reference. Rasters may have "
            "different extents/dimensions and still be aligned - only pixel "
            "size and origin phase matter. Reports mismatches in the log.\n\n"
            "Inputs:\n"
            "- Rasters: two or more raster layers to compare (first = reference)\n\n"
            "Output:\n"
            "- Alignment report printed to the log\n"
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterMultipleLayers(
            self.RASTERS, "Rasters to check (first = reference)",
            layerType=QgsProcessing.TypeRaster,
        ))

    def processAlgorithm(self, parameters, context, feedback):
        layers = self.parameterAsLayerList(parameters, self.RASTERS, context)
        if len(layers) < 2:
            feedback.reportError("Select at least two rasters to compare.")
            return {}

        infos = []
        for layer in layers:
            ds = gdal.Open(layer.source())
            if ds is None:
                feedback.reportError(f"Could not open raster with GDAL: {layer.name()} ({layer.source()})")
                return {}
            gt = ds.GetGeoTransform()
            infos.append({
                "name":    layer.name(),
                "origin_x": gt[0],
                "origin_y": gt[3],
                "pixel_w":  abs(gt[1]),
                "pixel_h":  abs(gt[5]),
                "cols":     ds.RasterXSize,
                "rows":     ds.RasterYSize,
            })
            ds = None

        feedback.pushInfo("=== Raster Alignment Report ===")
        for info in infos:
            feedback.pushInfo(
                f"{info['name']}: "
                f"origin=({info['origin_x']}, {info['origin_y']}), "
                f"pixel=({info['pixel_w']}, {info['pixel_h']}), "
                f"size={info['cols']}x{info['rows']}"
            )

        ref = infos[0]
        feedback.pushInfo(f"\nReference: {ref['name']}")
        tol = 1e-6
        all_match = True

        for info in infos[1:]:
            mismatches = []

            if abs(info['pixel_w'] - ref['pixel_w']) > tol or abs(info['pixel_h'] - ref['pixel_h']) > tol:
                mismatches.append(
                    f"pixel size ({info['pixel_w']}x{info['pixel_h']} vs {ref['pixel_w']}x{ref['pixel_h']})"
                )
            else:
                # Only meaningful to check phase if pixel size actually matches
                dx = (info['origin_x'] - ref['origin_x']) / ref['pixel_w']
                dy = (info['origin_y'] - ref['origin_y']) / ref['pixel_h']
                if abs(dx - round(dx)) > tol or abs(dy - round(dy)) > tol:
                    mismatches.append(
                        f"grid phase (offset {dx:.4f}, {dy:.4f} px from reference - not a whole-pixel offset)"
                    )

            if mismatches:
                feedback.reportError(f"MISMATCH — {info['name']}: {'; '.join(mismatches)}")
                all_match = False
            else:
                feedback.pushInfo(f"OK — {info['name']}: aligned with reference")

        if all_match:
            feedback.pushInfo("\nAll rasters are aligned.")
        else:
            feedback.reportError("\nAlignment issues detected — see above.")

        return {}