# -*- coding: utf-8 -*-

from tree.RiverNetwork import _NumpyArrayHolder
from tree.RiverNetwork import Reach
from tree.TreeTools import createFullTreeTableFromShapefile

import arcpy
import numpy as np

class FullReach(Reach):
    def __init__(self, rivernetwork, shape, data):
        Reach.__init__(self, rivernetwork, shape, data)

    def get_upstreamnextpts(self, collection):
        # Return the first points in the upstream reaches (list of points)
        list1 = self.rivernetwork._numpyarraylinks[
            self.rivernetwork._numpyarraylinks[self.rivernetwork.IDlink1name] == self.id]
        returnlist = []

        for junction in list1:
            sortedlist = np.sort(
                collection._numpyarray[collection._numpyarray[collection.dict_attr_fields['reach_id']] == junction[self.rivernetwork.IDlink2name]],
                order=collection.dict_attr_fields['dist'])


            if str(junction[self.rivernetwork.IDlink_orientationname]) == "END-TO-START" :
                if len(sortedlist) > 0:
                    ptid = sortedlist[collection.dict_attr_fields['id']][0]
                    returnlist.append(collection._points[collection._points['id'] == ptid]['object'][0])
                else:
                    # recursive call if there are no points on the reach
                    print("recursive from "+str(junction[self.rivernetwork.IDlink1name])+" to "+str(junction[self.rivernetwork.IDlink2name]))
                    returnlist.extend(self.rivernetwork.get_reach(junction[self.rivernetwork.IDlink2name]).get_upstreamnextpts(collection))
            elif str(junction[self.rivernetwork.IDlink_orientationname]) == "END-TO-END" :
                if len(sortedlist) > 0:
                    ptid = sortedlist[collection.dict_attr_fields['id']][-1]
                    returnlist.append(collection._points[collection._points['id'] == ptid]['object'][0])
                else:
                    print("recursive inverse from " + str(junction[self.rivernetwork.IDlink1name]) + " to " + str(
                        junction[self.rivernetwork.IDlink2name]))
                    returnlist.extend(
                        self.rivernetwork.get_reach(junction[self.rivernetwork.IDlink2name]).get_downstreamnextpts(
                            collection))



        list2 = self.rivernetwork._numpyarraylinks[
            self.rivernetwork._numpyarraylinks[self.rivernetwork.IDlink2name] == self.id]
        for junction in list2:
            sortedlist = np.sort(
                collection._numpyarray[collection._numpyarray[collection.dict_attr_fields['reach_id']] == junction[
                    self.rivernetwork.IDlink1name]],
                order=collection.dict_attr_fields['dist'])


            if str(junction[self.rivernetwork.IDlink_orientationname])== "START-TO-END":
                if len(sortedlist) > 0:
                    ptid = sortedlist[collection.dict_attr_fields['id']][0]
                    returnlist.append(collection._points[collection._points['id'] == ptid]['object'][0])
                else:
                    print("recursive from " + str(junction[self.rivernetwork.IDlink2name]) + " to " + str(
                        junction[self.rivernetwork.IDlink1name]))
                    returnlist.extend(
                        self.rivernetwork.get_reach(junction[self.rivernetwork.IDlink1name]).get_upstreamnextpts(
                            collection))
            elif str(junction[self.rivernetwork.IDlink_orientationname]) == "END-TO-END":
                if len(sortedlist) > 0:
                    ptid = sortedlist[collection.dict_attr_fields['id']][-1]
                    returnlist.append(collection._points[collection._points['id'] == ptid]['object'][0])
                else:
                    print("recursive inverse from " + str(junction[self.rivernetwork.IDlink2name]) + " to " + str(
                        junction[self.rivernetwork.IDlink1name]))
                    returnlist.extend(
                        self.rivernetwork.get_reach(junction[self.rivernetwork.IDlink1name]).get_downstreamnextpts(
                            collection))

        return returnlist

    def get_downstreamnextpts(self, collection):
        # Return the first points in the downstream reaches (list of points)
        list1 = self.rivernetwork._numpyarraylinks[
            self.rivernetwork._numpyarraylinks[self.rivernetwork.IDlink1name] == self.id]
        returnlist = []
        for junction in list1:
            sortedlist = np.sort(
                collection._numpyarray[collection._numpyarray[collection.dict_attr_fields['reach_id']] == junction[
                    self.rivernetwork.IDlink2name]],
                order=collection.dict_attr_fields['dist'])


            if junction[self.rivernetwork.IDlink_orientationname] == "START-TO-START":
                if len(sortedlist) > 0:
                    ptid = sortedlist[collection.dict_attr_fields['id']][0]
                    returnlist.append(collection._points[collection._points['id'] == ptid]['object'][0])
                else:
                    # recursive call if there are no points on the reach
                    print("recursive inverse from " + str(junction[self.rivernetwork.IDlink1name]) + " to " + str(
                        junction[self.rivernetwork.IDlink2name]))
                    returnlist.extend(
                        self.rivernetwork.get_reach(junction[self.rivernetwork.IDlink2name]).get_upstreamnextpts(
                            collection))
            elif junction[self.rivernetwork.IDlink_orientationname] == "START-TO-END":
                if len(sortedlist) > 0:
                    ptid = sortedlist[collection.dict_attr_fields['id']][-1]
                    returnlist.append(collection._points[collection._points['id'] == ptid]['object'][0])
                else:
                    print("recursive from " + str(junction[self.rivernetwork.IDlink1name]) + " to " + str(
                        junction[self.rivernetwork.IDlink2name]))
                    returnlist.extend(
                        self.rivernetwork.get_reach(junction[self.rivernetwork.IDlink2name]).get_downstreamnextpts(
                            collection))


        list2 = self.rivernetwork._numpyarraylinks[
            self.rivernetwork._numpyarraylinks[self.rivernetwork.IDlink2name] == self.id]
        for junction in list2:
            sortedlist = np.sort(
                collection._numpyarray[collection._numpyarray[collection.dict_attr_fields['reach_id']] == junction[
                    self.rivernetwork.IDlink1name]],
                order=collection.dict_attr_fields['dist'])


            if junction[self.rivernetwork.IDlink_orientationname] == "START-TO-START":
                if len(sortedlist) > 0:
                    ptid = sortedlist[collection.dict_attr_fields['id']][0]
                    returnlist.append(collection._points[collection._points['id'] == ptid]['object'][0])
                else:
                    print("recursive inverse from " + str(junction[self.rivernetwork.IDlink2name]) + " to " + str(
                        junction[self.rivernetwork.IDlink1name]))
                    returnlist.extend(
                        self.rivernetwork.get_reach(junction[self.rivernetwork.IDlink1name]).get_upstreamnextpts(
                            collection))
            elif junction[self.rivernetwork.IDlink_orientationname] == "END-TO-START":
                if len(sortedlist) > 0:
                    ptid = sortedlist[collection.dict_attr_fields['id']][-1]
                    returnlist.append(collection._points[collection._points['id'] == ptid]['object'][0])
                else:
                    print("recursive from " + str(junction[self.rivernetwork.IDlink2name]) + " to " + str(
                        junction[self.rivernetwork.IDlink1name]))
                    returnlist.extend(
                        self.rivernetwork.get_reach(junction[self.rivernetwork.IDlink1name]).get_downstreamnextpts(
                            collection))

        return returnlist



class FullRiverNetwork(_NumpyArrayHolder):


    IDlink1name = "RID1"
    IDlink2name = "RID2"
    IDlink_orientationname = "Orientation"

    dict_attr_fields = {"id": "RID",
                       "length": "SHAPE@LENGTH",
                       "main": "Main"
                       }


    def __init__(self):
        _NumpyArrayHolder.__init__(self)
        self.points_collection = {}
        self.dict_attr_fields = FullRiverNetwork.dict_attr_fields.copy()

    def load_data(self, reaches_shapefile):
        # Include creation of the link table (not stored on disk, as opposed to RiverNetwork) from the shapefile

        self.shapefile = reaches_shapefile
        self.SpatialReference = arcpy.Describe(reaches_shapefile).SpatialReference

        # on initialise les matrices Numpy
        # matrice de base
        try:
            self._numpyarray = arcpy.da.FeatureClassToNumPyArray(reaches_shapefile, list(self.dict_attr_fields.values()), null_value=-9999)

        except RuntimeError:
            raise RuntimeError("Error loading shapefile. Make sure the fields names match.")
        # the list of valid_ids is used in case secondary channels are not included
        valid_ids = self._numpyarray[self.dict_attr_fields['id']]
        # matrice des liaisons amont-aval
        self._numpyarraylinks = createFullTreeTableFromShapefile(reaches_shapefile, self.dict_attr_fields['id'], self.IDlink1name, self.IDlink2name, self.IDlink_orientationname)

        # matrice contenant les instances de Reach
        self._reaches = np.empty(self._numpyarray.shape[0], dtype=[('id', 'i4'),('object', 'O')])
        # In order to populate the self._reaches array, we could iterate through the self._numpyarray
        # It's quicker, but with the SearchCursor we can retrieve the Shape object, which could be needed)
        listfields = list(self.dict_attr_fields.values())
        listfields_withshape = listfields[:] # deep copy the list
        listfields_withshape.append("SHAPE@")
        reachescursor = arcpy.da.SearchCursor(reaches_shapefile, listfields_withshape)
        i = 0
        for reach in reachescursor:
            data = {}
            for field in listfields:
                data[field]=reach[listfields_withshape.index(field)]
            if data[self.dict_attr_fields['id']] in valid_ids.tolist():
                self._reaches[i]['id'] = data[self.dict_attr_fields['id']]
                self._reaches[i]['object'] = FullReach(self, reach[-1], data)
                i+=1


    def get_reach(self, id):
        return self._reaches[self._reaches['id'] == id]['object'][0]





