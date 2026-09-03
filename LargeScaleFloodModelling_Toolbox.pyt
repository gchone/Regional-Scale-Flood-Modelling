# -*- coding: utf-8 -*-

from pathlib import Path
import sys

import arcpy

_ROOT = Path(__file__).resolve().parent
sys.path.append(str(_ROOT))
sys.path.append(str(_ROOT / "Regional-Scale-Flood-Modelling-ArcGIS"))

from ArcGIS_WatershedScaleDEMprocessing_Interface import *
from ArcGIS_BatchProcessAggregate_Interface import *
from ArcGIS_BridgeCorrection_Interface import *
from ArcGIS_FlowDirectionForWS_Interface import *
from ArcGIS_CreateFromPointsAndSplits_Interface import *
from ArcGIS_CreateNetworkFromFlowDir_Interface import *
from ArcGIS_CreatePointsAlongReaches_Interface import *
from ArcGIS_ExtractWaterSurface_Interface import *
from ArcGIS_AssignPointToClosestPointOnRoute_Interface import *
from ArcGIS_WidthByCrossSections_Interface import *
from ArcGIS_WidthPostProc_Interface import *
from ArcGIS_BedAssessment_Interface import *
from ArcGIS_LisfloodDataConversion_Interface import *
from ArcGIS_Tiling_Interface import *
from ArcGIS_HydraulicSimPrep_Interface import *
from ArcGIS_RunHydraulicSim_Interface import *

class Toolbox(object):
    def __init__(self):

        self.label = "Large Scale Flood Modeling Toolbox"
        self.alias = ""

        self.tools = [ArcGIS_WatershedScaleDEMprocessing_Interface, BatchAggregate, BridgeCorrection, FlowDirForWS,
                      CreateFromPointsAndSplits, CreateNetworkFromFlowDir, CreatePointsAlongReaches, ArcGIS_ExtractWaterSurface_Interface,
                      ArcGIS_AssignPointToClosestPointOnRoute_Interface, ArcGIS_WidthByCrossSections_Interface,
                      ArcGIS_WidthPostProc_Interface, ArcGIS_BedAssessment_Interface, ArcGIS_LisfloodDataConversion_Interface, ArcGIS_HydraulicSimPrep_Interface,
                      CreateZonesWlakes, ArcGIS_RunHydraulicSim_Interface]
