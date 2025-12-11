# -*- coding: utf-8 -*-

import arcpy


from OrderReaches_Interface import *

from FlowDirNetwork_Interface import *
from ExtractDischarges_Interface import *
from SpatializeQ_Interface import *




class Toolbox(object):
    def __init__(self):

        self.label = "Metatools for linear referencing"
        self.alias = ""

        self.tools = [OrderReaches, FlowDirNetwork, ExtractDischarges, SpatializeQ]

