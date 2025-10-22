# -*- coding: utf-8 -*-

import arcpy

from WatershedScaleDEMprocessing_Interface import *
from DEMprocessing_Interface import *
from BridgeCorrection_Interface import *
from FlowDirForWS_Interface import *
from CreateFromPointsAndSplits_Interface import *
from TreeFromFlowDir_Interface import *
from PlacePointsAlongReaches_Interface import *
from ExtractWaterSurface_Interface import *
from SpatializeQLiDAR_from_gauging_stations_Interface import *
from AssignPointToClosestPointOnRoute_Interface import *
from LargeurParTransect_Interface import *
from WidthPostProc_Interface import *
from BedAssessment_Interface import *
from LisfloodDataConversion_Interface import *

class Toolbox(object):
    def __init__(self):

        self.label = "Large Scale Flood Modeling Toolbox"
        self.alias = ""

        self.tools = [WatershedScaleDEMprocessing, BatchAggregate, BridgeCorrection, FlowDirForWS,
                      CreateFromPointsAndSplits, TreeFromFlowDir, PlacePointsAlongReaches, ExtractWaterSurface,
                      SpatializeQLiDAR_gauging_stations, AssignPointToClosestPointOnRoute, LargeurParTransect,
                      WidthPostProc, BedAssessment, LisfloodDataConversion]
