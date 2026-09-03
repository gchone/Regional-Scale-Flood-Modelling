# -*- coding: utf-8 -*-

from pathlib import Path
import sys

import arcpy

_ROOT = Path(__file__).resolve().parent
sys.path.append(str(_ROOT))
sys.path.append(str(_ROOT / "Regional-Scale-Flood-Modelling-ArcGIS"))

from ArcGIS_RelateNetworks_Interface import *
from ArcGIS_LocatePointsAlongRoutes_Interface import *
from ArcGIS_CreateNetworkFromFC_Interface import *
from ArcGIS_WSsmoothing_Interface import *
from ArcGIS_LocateMostDownstreamPoints_Interface import *
from ArcGIS_InterpolatePoints_Interface import *
from ArcGIS_TopologicalRelateNetworks_Interface import *
from ArcGIS_D4FlowDirection_Interface import *
from ArcGIS_OrderReaches_Interface import *
from ArcGIS_FlowDirectionNetwork_Interface import *
from ArcGIS_ExtractDischarges_Interface import *
from ArcGIS_SpatializeQ_Interface import *
from ArcGIS_SpatializeQLIDARFromGaugingStations_Interface import *
from ArcGIS_SpatializeQFloodFromGaugingStations_Interface import *

class Toolbox(object):
    def __init__(self):

        self.label = "Large Scale Flood Modeling Toolbox - detailed processing"
        self.alias = ""

        self.tools = [ArcGIS_D4FlowDirection_Interface, TopologicalRelateNetworks, ArcGIS_InterpolatePoints_Interface, RelateNetworks, ArcGIS_LocatePointsAlongRoutes_Interface, CreateNetworkFromFC, LocateMostDownstreamPoints, ArcGIS_WSsmoothing_Interface, OrderReaches, FlowDirectionNetwork, ArcGIS_ExtractDischarges_Interface, SpatializeQ, SpatializeQLIDARFromGaugingStations, SpatializeQFloodFromGaugingStations]
