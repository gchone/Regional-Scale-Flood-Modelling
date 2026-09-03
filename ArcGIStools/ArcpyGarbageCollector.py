# -*- coding: utf-8 -*-


import arcpy
import os

class _GarbageManager(object):

    __instance = None
    __garbagelist = []

    @staticmethod
    def getInstance():
        """ Static access method. """
        if _GarbageManager.__instance == None:
            _GarbageManager()
        return _GarbageManager.__instance

    def __init__(self):
        """ Virtually private constructor. """
        if _GarbageManager.__instance != None:
            raise Exception("This class is a singleton!")
        else:
            _GarbageManager.__instance = self
            self.inmemoryindex = 0

    def add_to_garbagebin(self, path):
        self.__garbagelist.append(path)

    def empty_garbagebin(self):
        for item in self.__garbagelist:
            if arcpy.Exists(item):
                arcpy.Delete_management(item)
        self.__garbagelist = []

    def remove(self, item):
        if item in self.__garbagelist:
            if arcpy.Exists(item):
                arcpy.Delete_management(item)
            self.__garbagelist.remove(item)

def CreateScratchName(prefix, data_type, workspace):
    # "ArcInfoTable" doesn't work for creating tables with arcpy.CreateScratchName in gdb. This function allow it.
    # Also, in memory object to not receive an unique id
    if workspace=="in_memory":
        gb = _GarbageManager.getInstance()
        gb.inmemoryindex += 1
        return arcpy.CreateScratchName(prefix+str(gb.inmemoryindex), data_type=data_type, workspace=workspace)
    else:
        if data_type == "ArcInfoTable" or data_type == "FeatureClass":
            if arcpy.Describe(workspace).dataType == "Workspace":
                # In a Geodatabase, tables name should be created with data_type == "FeatureClass"
                # It's still not working properly, so the loop with Exists fixes that
                name = arcpy.CreateScratchName(prefix, data_type="FeatureClass", workspace=workspace)
                shortname = os.path.basename(name)[:len(prefix)]
                index = int(os.path.basename(name)[len(prefix):])
                while arcpy.Exists(name):
                    index += 1
                    name = os.path.join(workspace, shortname+str(index))
            else: #arcpy.Describe(workspace).dataType == "Folder"
                name = arcpy.CreateScratchName(prefix, data_type=data_type, workspace=workspace)
        else: #data_type == "RasterDataset"
            name = arcpy.CreateScratchName(prefix, data_type=data_type, workspace=workspace)
        AddToGarbageBin(name)
        return name



def CleanAllTempFiles():
    gb = _GarbageManager.getInstance()
    gb.empty_garbagebin()

def CleanTempFile(file):
    gb = _GarbageManager.getInstance()
    gb.remove(file)

def AddToGarbageBin(item):
    gb = _GarbageManager.getInstance()
    gb.add_to_garbagebin(item)
