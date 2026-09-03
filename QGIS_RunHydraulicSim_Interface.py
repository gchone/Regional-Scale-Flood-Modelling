from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))

from RunHydraulicSim import execute_RunHydraulicSim
import QGIStools
from QGIS_Messages import Messages

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessing,
)


class QGIS_RunHydraulicSim(QgsProcessingAlgorithm):
    TILES_FOLDER = "TILES_FOLDER"
    INBCI_LAYERS = "INBCI_LAYERS"
    SIM_FOLDER = "SIM_FOLDER"
    LISFLOOD_FOLDER = "LISFLOOD_FOLDER"
    VOUTPUT = "VOUTPUT"
    LAKES = "LAKES"
    LAKES_RASTER = "LAKES_RASTER"
    ZFIELDS = "ZFIELDS"
    CHANNEL_MANNING = "CHANNEL_MANNING"
    SIM_TIME = "SIM_TIME"
    CFL = "CFL"
    ZBED = "ZBED"
    LOG = "LOG"

    def name(self):
        return "run_hydraulic_simulations"

    def displayName(self):
        return "Run hydraulic simulations with LISFLOOD-FP"

    def group(self):
        return "Large Scale Flood Modelling Toolbox"

    def groupId(self):
        return "large_scale_flood_modelling_toolbox"

    def createInstance(self):
        return QGIS_RunHydraulicSim()

    def shortHelpString(self):
        return (
            "Run hydraulic simulations with LISFLOOD-FP\n\n"
            "Runs LISFLOOD-FP tile by tile for each selected discharge layer. "
            "Behavior is aligned to the ArcGIS-authoritative tool: discharge layers "
            "and downstream boundary fields are paired by selection order, mass-balance "
            "checks are warnings only, and simulations that stop before steady state "
            "are retried once without -steady/-steadytol.\n\n"
            "Inputs:\n"
            "- Tiles folder: contains inbci/outbci/envelopezones plus zone rasters\n"
            "- Inbci layers: one discharge layer per simulation (typically joined copies of inbci)\n"
            "- Simulations folder: contains LISFLOOD-FP templates and receives outputs\n"
            "- LISFLOOD-FP folder: folder containing lisflood.exe\n"
            "- Output flow velocity?: also produce Vx/Vy rasters\n"
            "- Downstream boundary polygons (lakes)\n"
            "- Optional downstream boundary raster: retained for compatibility but ignored\n"
            "- Downstream boundary condition fields: select one per discharge, in the same order\n"
            "- Channel Manning's n (default 0.03)\n"
            "- Maximum simulation time in seconds (default 300000)\n"
            "- Courant-Friedrichs-Lewy condition (default 0.5)\n"
            "- D4 bed elevation raster\n\n"
            "Outputs:\n"
            "- Log file plus res_<discharge>.tif mosaics in the simulations folder\n"
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessingParameterFile,
            QgsProcessingParameterVectorLayer,
            QgsProcessingParameterField,
            QgsProcessingParameterMultipleLayers,
            QgsProcessingParameterRasterLayer,
            QgsProcessingParameterBoolean,
            QgsProcessingParameterNumber,
            QgsProcessingParameterFileDestination,
        )

        self.addParameter(QgsProcessingParameterFile(
            self.TILES_FOLDER,
            "Tiles folder",
            behavior=QgsProcessingParameterFile.Folder,
        ))
        self.addParameter(QgsProcessingParameterMultipleLayers(
            self.INBCI_LAYERS,
            "Inbci layers, one per discharge",
            layerType=QgsProcessing.TypeVectorPoint,
        ))
        self.addParameter(QgsProcessingParameterFile(
            self.SIM_FOLDER,
            "Simulations folder",
            behavior=QgsProcessingParameterFile.Folder,
        ))
        self.addParameter(QgsProcessingParameterFile(
            self.LISFLOOD_FOLDER,
            "LISFLOOD-FP folder",
            behavior=QgsProcessingParameterFile.Folder,
        ))
        self.addParameter(QgsProcessingParameterBoolean(
            self.VOUTPUT,
            "Output flow velocity (Vx/Vy)?",
            defaultValue=False,
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.LAKES,
            "Downstream boundary polygons (lakes)",
            [QgsProcessing.TypeVectorPolygon],
        ))
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.LAKES_RASTER,
            "Optional: raster used for downstream boundary condition (ignored; retained for compatibility)",
            optional=True,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.ZFIELDS,
            "Downstream boundary condition fields on lakes (one per discharge, same order)",
            parentLayerParameterName=self.LAKES,
            allowMultiple=True,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.CHANNEL_MANNING,
            "Channel Manning's n",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=0.03,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.SIM_TIME,
            "Maximum simulation time (s)",
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=300000,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.CFL,
            "Courant-Friedrichs-Lewy condition",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=0.5,
        ))
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.ZBED,
            "D4 bed elevation raster",
        ))
        self.addParameter(QgsProcessingParameterFileDestination(
            self.LOG,
            "Log file",
            fileFilter="Text files (*.txt)",
        ))

    def processAlgorithm(self, parameters, context, feedback):
        tiles_folder = self.parameterAsFile(parameters, self.TILES_FOLDER, context)
        inbci_layers = self.parameterAsLayerList(parameters, self.INBCI_LAYERS, context)
        sim_folder = self.parameterAsFile(parameters, self.SIM_FOLDER, context)
        lisflood_folder = self.parameterAsFile(parameters, self.LISFLOOD_FOLDER, context)
        voutput = self.parameterAsBoolean(parameters, self.VOUTPUT, context)
        lakes = self.parameterAsVectorLayer(parameters, self.LAKES, context)
        lakes_raster = self.parameterAsRasterLayer(parameters, self.LAKES_RASTER, context)
        zfields = self.parameterAsStrings(parameters, self.ZFIELDS, context)
        channel_manning = self.parameterAsDouble(parameters, self.CHANNEL_MANNING, context)
        sim_time = self.parameterAsInt(parameters, self.SIM_TIME, context)
        cfl = self.parameterAsDouble(parameters, self.CFL, context)
        zbed = self.parameterAsRasterLayer(parameters, self.ZBED, context)
        log_path = self.parameterAsFileOutput(parameters, self.LOG, context)

        if not inbci_layers:
            raise QgsProcessingException("Select at least one inbci layer")
        if not zfields:
            raise QgsProcessingException("Select at least one downstream boundary condition field on the lakes layer")
        if len(inbci_layers) != len(zfields):
            raise QgsProcessingException("Number of downstream boundary condition should match the number of input discharges")
        if not all([lakes, zbed]):
            raise QgsProcessingException("One or more input layers are invalid")

        execute_RunHydraulicSim(
            tiles_folder=tiles_folder,
            simulations_folder=sim_folder,
            lisflood_folder=lisflood_folder,
            lakes=lakes,
            boundary_fields=zfields,
            output_velocity=voutput,
            simulation_time=sim_time,
            cfl=cfl,
            channel_manning=channel_manning,
            zbed=zbed,
            log_path=log_path,
            GIStools=QGIStools,
            messages=Messages(feedback),
            inbci_layers=inbci_layers,
            downstream_boundary_raster=lakes_raster.source() if lakes_raster is not None else None,
        )

        return {self.LOG: log_path}
