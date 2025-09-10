# -*- coding: utf-8 -*-

import arcpy

from RelateNetworks_Interface import *
from LocatePointsAlongRoutes_Interface import *
from LargeurParTransect_Interface import *

from AssignPointToClosestPointOnRoute_Interface import *
from CreateTreeFromShapefile_Interface import *
#from ChannelCorrection_Interface import *
from WSsmoothing_Interface import *


from LocateMostDownstreamPoints_Interface import *

from InterpolatePoints_Interface import *
from DownstreamSlope_Interface import *
from BedAssessmentOld_Interface import *
from TopologicalD8RelateNetworks_Interface import *
from CreateZones_Interface import *
from DefBci_Interface import *
from RunSim_Qlisted_Interface import *

from D8toD4_Interface import *
from SpatializeQ_rasters_Interface import *

class Toolbox(object):
    def __init__(self):

        self.label = "Large Scale Flood Modeling Toolbox - detailed processing"
        self.alias = ""

        self.tools = [SpatializeQ_rasters, D8toD4, RunSim_LISFLOOD, DefBciWithLateralWlakes_hdown, CreateZonesWlakes, TopologicalRelateNetworks, BedAssessmentIterations, DownstreamSlope, InterpolatePoints, RelateNetworks, LocatePointsAlongRoutes, LargeurParTransect, AssignPointToClosestPointOnRoute, CreateTreeFromShapefile,  LocateMostDownstreamPoints, WSsmoothing]

