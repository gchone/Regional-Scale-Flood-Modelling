# -*- coding: utf-8 -*-

import arcpy

from RelateNetworks_Interface import *
from LocatePointsAlongRoutes_Interface import *
from CreateTreeFromShapefile_Interface import *
from WSsmoothing_Interface import *
from LocateMostDownstreamPoints_Interface import *
from InterpolatePoints_Interface import *
from DownstreamSlope_Interface import *
from TopologicalD8RelateNetworks_Interface import *
from D8toD4_Interface import *
from SpatializeQ_rasters_Interface import *
from OrderReaches_Interface import *
from FlowDirNetwork_Interface import *
from ExtractDischarges_Interface import *
from SpatializeQ_Interface import *

class Toolbox(object):
    def __init__(self):

        self.label = "Large Scale Flood Modeling Toolbox - detailed processing"
        self.alias = ""

        self.tools = [SpatializeQ_rasters, D8toD4, TopologicalRelateNetworks, DownstreamSlope, InterpolatePoints, RelateNetworks, LocatePointsAlongRoutes, CreateTreeFromShapefile,  LocateMostDownstreamPoints, WSsmoothing, OrderReaches, FlowDirNetwork, ExtractDischarges, SpatializeQ]

