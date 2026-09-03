from pathlib import Path
import os
import sys

sys.path.append(str(Path(__file__).resolve().parent))

from HydraulicSimPrep import prepare_hydraulic_sim
import QGIStools
from QGIS_Messages import Messages

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessing,
)


class QGIS_HydraulicSimPrep(QgsProcessingAlgorithm):
    FLOWDIR = "FLOWDIR"
    FLOWACC = "FLOWACC"
    PERCENT = "PERCENT"
    ZONES_FOLDER = "ZONES_FOLDER"
    DEM = "DEM"
    WIDTH = "WIDTH"
    ZBED = "ZBED"
    MANNING = "MANNING"
    MASK = "MASK"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"

    def name(self):
        return "hydraulicsimprep"

    def displayName(self):
        return "Hydraulic simulations preparation"

    def group(self):
        return "Large Scale Flood Modelling Toolbox"

    def groupId(self):
        return "large_scale_flood_modelling_toolbox"

    def createInstance(self):
        return QGIS_HydraulicSimPrep()

    def shortHelpString(self):
        return (
            "Hydraulic simulations preparation\n\n"
            "Creates LISFLOOD-FP input files for each tile: clips the DEM to each "
            "zone's bounding-box envelope, traces the flow path from each zone's "
            "source point to find the exit point and detect lateral inflow points, "
            "writes a .bci boundary condition file per zone, and clips width, bed "
            "elevation, Manning's n, and channel mask rasters to ASCII for LISFLOOD.\n\n"
            "Inputs:\n"
            "- Flow direction: watershed-scale D8 flow direction raster (e.g. Lisflood_inputs\\lidar10m_fd)\n"
            "- Flow accumulation: watershed-scale flow accumulation raster (e.g. Lisflood_inputs\\lidar10m_facc)\n"
            "- Drainage area variation for discharge correction (%): flow accumulation increase threshold used to detect lateral inflow points (default 1)\n"
            "- Tiles folder: folder containing polyzones.gpkg and sourcepoints.gpkg "
            "(from the Tiling tool); zone{N}.tif rasters are also written here\n"
            "- DEM: watershed-scale DEM (e.g. lidar10m_avg)\n"
            "- D4 width, D4 bed elevation, floodplain Manning's n, channel mask: (e.g. Lisflood_inputs\\widthD4, bed, n_floodplain, mask)"
            "rasters clipped per zone and converted to ASCII\n"
            "- Output folder: destination for .bci and ASCII files (Simulations\\sims)\n\n"
            "The downstream boundary condition (exit window into each tile's .bci "
            "file) is no longer computed here — it's computed at run time by Run "
            "Hydraulic Simulations, using the already-simulated downstream tile's "
            "actual result raster.\n"
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessingParameterRasterLayer,
            QgsProcessingParameterFile,
            QgsProcessingParameterNumber,
            QgsProcessingParameterFolderDestination,
        )

        self.addParameter(QgsProcessingParameterRasterLayer(
            self.FLOWDIR, "Flow direction (lidar10m_fd)",
        ))
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.FLOWACC, "Flow accumulation (lidar10m_facc)",
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.PERCENT, "Drainage area variation for discharge correction (%)",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=1.0,
        ))
        self.addParameter(QgsProcessingParameterFile(
            self.ZONES_FOLDER, r"Tiles folder (polyzones.gpkg, sourcepoints.gpkg) (Tiles\)",
            behavior=QgsProcessingParameterFile.Folder,
        ))
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.DEM, "DEM (lidar10m_avg)",
        ))
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.WIDTH, "D4 width (widthD4)",
        ))
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.ZBED, "D4 bed elevation (bed)",
        ))
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.MANNING, "Floodplain Manning's n (n_floodplain)",
        ))
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.MASK, "Channel mask (mask)",
        ))
        self.addParameter(QgsProcessingParameterFolderDestination(
            self.OUTPUT_FOLDER, r"Output folder for .bci and ASCII files (Simulations\sims)",
        ))

    def processAlgorithm(self, parameters, context, feedback):
        flowdir = self.parameterAsRasterLayer(parameters, self.FLOWDIR, context)
        flowacc = self.parameterAsRasterLayer(parameters, self.FLOWACC, context)
        zones_folder = self.parameterAsFile(parameters, self.ZONES_FOLDER, context)
        dem = self.parameterAsRasterLayer(parameters, self.DEM, context)
        width = self.parameterAsRasterLayer(parameters, self.WIDTH, context)
        zbed = self.parameterAsRasterLayer(parameters, self.ZBED, context)
        manning = self.parameterAsRasterLayer(parameters, self.MANNING, context)
        mask = self.parameterAsRasterLayer(parameters, self.MASK, context)
        percent = self.parameterAsDouble(parameters, self.PERCENT, context)
        output_folder = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)

        if not all([flowdir, flowacc, dem, width, zbed, manning, mask]):
            raise QgsProcessingException("One or more input rasters are invalid")
        if not zones_folder or not os.path.isdir(zones_folder):
            raise QgsProcessingException("Tiles folder is invalid")

        os.makedirs(output_folder, exist_ok=True)
        prepare_hydraulic_sim(
            flowdir_raster=flowdir,
            flowacc_raster=flowacc,
            percent=percent,
            zones_folder=zones_folder,
            dem_raster=dem,
            width_raster=width,
            zbed_raster=zbed,
            manning_raster=manning,
            mask_raster=mask,
            output_folder=output_folder,
            GIStools=QGIStools,
            messages=Messages(feedback),
        )
        return {self.OUTPUT_FOLDER: output_folder}


HydraulicSimPrep = QGIS_HydraulicSimPrep
