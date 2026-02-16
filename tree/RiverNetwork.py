# -*- coding: utf-8 -*-


import arcpy

import numpy as np
import os
import numpy.lib.recfunctions as rfn
import ArcpyGarbageCollector as gc

class BrowsingStopper():
    # Instances of this class are used to be passed as an argument to generators, when browsing points from upstream to
    #  downstream.
    def __init__(self):
        self.break_generator = False

class _NumpyArrayHolder(object):

    def __init__(self):
        self._variablesset = set([])
        self._variablestype = {}

    def get_SavedVariables(self):
        return self._variablesset

    def add_SavedVariable(self, name, dtype, maxlength = None, fieldname = None):
        # creating a new attribute
        # dtype can be "float", "int" or "str"
        # if "str", a maxlength must be provided
        if fieldname is None:
            fieldname = name
        if dtype=="int" or dtype=="float":
            self._variablesset.add(name)
            self._variablestype[name] = [dtype, fieldname]
        elif dtype=="str" and maxlength is not None:
            self._variablesset.add(name)
            self._variablestype[name] = [dtype, fieldname, maxlength]
        else:
            # if the attribute is not an int, a float or a string, it can't be saved
            raise TypeError


    def delete_SavedVariable(self, name):
        self._variablesset.remove(name)
        self._variablestype.pop(name)

class RiverNetwork(_NumpyArrayHolder):

    reaches_linkfieldup = "UpID"
    reaches_linkfielddown = "DownID"

    dict_attr_fields = {"id": "RID",
                       "length": "SHAPE@LENGTH",
                       }
    # dict_attr_fields can also have a "main" key, when secondary channels are included

    def __init__(self):
        _NumpyArrayHolder.__init__(self)
        self.points_collection = {}
        self.dict_attr_fields = RiverNetwork.dict_attr_fields.copy()

    def load_data(self, reaches_shapefile, reaches_linktable, load_secondary_channel = False):
        self.shapefile = reaches_shapefile
        self.SpatialReference = arcpy.Describe(reaches_shapefile).SpatialReference

        # on initialise les matrices Numpy
        # matrice de base
        try:
            self._numpyarray = arcpy.da.FeatureClassToNumPyArray(reaches_shapefile, list(self.dict_attr_fields.values()), null_value=-9999)
            if "main" in self.dict_attr_fields.keys() and not load_secondary_channel:
                self._numpyarray = np.delete(self._numpyarray, self._numpyarray[self.dict_attr_fields['main']]==0)
        except RuntimeError:
            raise RuntimeError("Error loading shapefile. Make sure the fields names match.")
        # the list of valid_ids is used in case secondary channels are not included
        valid_ids = self._numpyarray[self.dict_attr_fields['id']]
        # matrice des liaisons amont-aval
        self._numpyarraylinks = arcpy.da.TableToNumPyArray(reaches_linktable, [self.reaches_linkfielddown, self.reaches_linkfieldup])
        if "main" in self.dict_attr_fields.keys() and not load_secondary_channel:
            self._numpyarraylinks = np.delete(self._numpyarraylinks, np.invert(np.in1d(self._numpyarraylinks[self.reaches_linkfieldup],valid_ids)))
            self._numpyarraylinks = np.delete(self._numpyarraylinks,
                                              np.invert(np.in1d(self._numpyarraylinks[self.reaches_linkfielddown], valid_ids)))
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
                self._reaches[i]['object'] = Reach(self, reach[-1], data)
                i+=1
        # for i in range(self._numpyarray.shape[0]):
        #     self._reaches[i]['id'] = self._numpyarray[i][self._dict_attr_fields['id']]
        #     self._reaches[i]['object'] = Reach(self, self._numpyarray[i][self._dict_attr_fields['id']])

        # Tried different things to add a field with the objects to the _numpyarray but did not succeed:
        #self._numpyarray = rfn.merge_arrays([self._numpyarray, object_column], flatten=True)
        #rfn.append_fields(self._numpyarray, 'object', list)



    def get_downstream_ends(self):
        # Générateur. Retourne la liste des tronçons extrémités aval
        # Ce sont ceux qui ne sont pas présents dans "UpstreamRID" de _numpyarraylinks
        for id in np.setdiff1d(self._reaches['id'], self._numpyarraylinks[self.reaches_linkfieldup]):
            yield self._reaches[self._reaches['id'] == id]['object'][0]

    def get_upstream_ends(self):
        # Générateur. Retourne la liste des tronçons extrémités amont
        # Ce sont ceux qui ne sont pas présents dans "DownsstreamRID" de _numpyarraylinks
        for id in np.setdiff1d(self._reaches['id'], self._numpyarraylinks[self.reaches_linkfielddown]):
            yield self._reaches[self._reaches['id'] == id]['object'][0]

    def browse_reaches_down_to_up(self, prioritize_points_collection=None, prioritize_points_attribute=None, prioritize_reach_attribute=None, reverse=False):
        # Générateur. Trouve et retourne la liste de segments dans la matrice Numpy
        # La matrice numpy est interrogée pour fournir les tronçons dans l'ordre souhaitée. Optionnellement, si
        #     prioritize_points_attribute != None, l'ordre des tronçons retournés aux confluences est aussi déterminé.
        for downstream_end in self.get_downstream_ends():
            for item in self._recursive_browse_reaches(downstream_end, "DOWN_TO_UP", prioritize_points_collection, prioritize_points_attribute, prioritize_reach_attribute, reverse):
                yield item


    def browse_reaches_up_to_down(self, stopper=BrowsingStopper(), prioritize_reach_attribute = None, reverse=False):
        # Générateur. Trouve et retourne la liste de segments dans la matrice Numpy
        # La matrice numpy est interrogée pour fournir les tronçons dans l'ordre souhaitée.
        list_upstream_ends = list(self.get_upstream_ends())
        if prioritize_reach_attribute is not None:
            list_upstream_ends.sort(key=lambda r: getattr(r, prioritize_reach_attribute),
                                    reverse=reverse)
        for upstream_end in list_upstream_ends:
            stopper.break_generator = False
            for item in self._recursive_browse_reaches(upstream_end, "UP_TO_DOWN", None, None, None, None):
                if stopper.break_generator:
                    # When the stopper is set to end iteration, it must be for the current path (upstream to downstream)
                    #  but things should resume at the next upstream end.
                    break
                yield item

    def _recursive_browse_reaches(self, currentreach, orientation, prioritize_points_collection,
                                   prioritize_points_attribute, prioritize_reach_attribute, reverse):
        yield currentreach
        if orientation == "DOWN_TO_UP":
            upstream_list = list(currentreach.get_uptream_reaches())
            if prioritize_points_collection is not None:
                upstream_list.sort(key=lambda r: getattr(r.get_first_point(prioritize_points_collection), prioritize_points_attribute), reverse=reverse)
            elif prioritize_reach_attribute is not None:
                upstream_list.sort(key=lambda r: getattr(r, prioritize_reach_attribute),
                                   reverse=reverse)
            for reach in upstream_list:
                for item in self._recursive_browse_reaches(reach, orientation, prioritize_points_collection,
                                       prioritize_points_attribute, prioritize_reach_attribute, reverse):
                    yield item
        else:
            downstreamreach = currentreach.get_downstream_reach()
            if downstreamreach is not None:
                for item in self._recursive_browse_reaches(downstreamreach, orientation, prioritize_points_collection,
                                           prioritize_points_attribute, prioritize_reach_attribute, reverse):
                    yield item

    def get_reach(self, id):
        return self._reaches[self._reaches['id'] == id]['object'][0]

    def order_reaches_by_discharge(self, collection, discharge_name):
        order = 0
        for reach in self.browse_reaches_down_to_up(prioritize_points_collection=collection,
                                                        prioritize_points_attribute=discharge_name, reverse=True):
            reach.order = order
            order += 1

    def __str__(self):
        for downstream_end in self.get_downstream_ends():
            return downstream_end._recursiveprint("")


    def placePointsAtRegularInterval(self, interval, collection):
        # Place points at regular interval. The collection must be existing but must be empty
        tablename = gc.CreateScratchName("table", data_type="ArcInfoTable", workspace="in_memory")
        table = arcpy.CreateTable_management("in_memory", os.path.basename(tablename))
        arcpy.AddField_management(table, self.dict_attr_fields["id"], "LONG")
        arcpy.AddField_management(table, "MEAS", "DOUBLE")
        arcpy.AddField_management(table, "Distance", "DOUBLE")
        insert = arcpy.da.InsertCursor(table, [self.dict_attr_fields["id"], "MEAS", "Distance"])
        #insert = arcpy.da.InsertCursor(table, ["SHAPE@XY", network.dict_attr_fields["id"], "Distance"])
        for reach in self.browse_reaches_down_to_up():
            for dist in np.arange(0, reach.length, interval):
                insert.insertRow([reach.id, dist, 0])
        del insert
        collection.dict_attr_fields["id"]=arcpy.Describe(table).OIDFieldName
        collection.dict_attr_fields["reach_id"]=self.dict_attr_fields["id"]
        collection.load_table(table)






class _NumpyArrayFedObject(object):


    def __init__(self, numpyarray_holder, data):
        # The object can be fed by an id, or by its whole row from the numpyarray
        # Note: __dict__ is called to prevent infinite recursion linked with __getattr__/__setattr__
        self.__dict__["_numpyarray_holder"] = numpyarray_holder

        for attr, field in self._numpyarray_holder.dict_attr_fields.items():
            if isinstance(data[field], np.ndarray):
                self.__dict__[attr] = data[field][0]
            else:
                self.__dict__[attr] = data[field]


    def __setattr__(self, name, value):
        if name != "id" :
            if name in self._numpyarray_holder.dict_attr_fields.keys():
                # change la valeur dans la matrice Numpy pour
                array = self._numpyarray_holder._numpyarray
                # champ pour l'id:
                idfield = self._numpyarray_holder.dict_attr_fields['id']
                # champ pour la valeur:
                valuefield = self._numpyarray_holder.dict_attr_fields[name]
                array[valuefield][array[idfield] == self.id] = value
            # Following part removed: the attributes to be saved at set up manually
            # elif not name in self.__dict__:
            #     # creating a new attribute
            #     if isinstance(value, float) or isinstance(value, int):
            #         self._numpyarray_holder._variablesset.add(name)
            #         self._numpyarray_holder._variablestype[name] = ['float']
            #     elif isinstance(value, str):
            #         self._numpyarray_holder._variablesset.add(name)
            #         if name in self._numpyarray_holder._variablestype.keys():
            #             maxlength = max(len(value), self._numpyarray_holder._variablestype[name][1])
            #         else:
            #             maxlength = len(value)
            #         self._numpyarray_holder._variablestype[name] = ['str', maxlength]
            # if the attribute is not an int, a float or a string, it is not added to the list and can't be saved


        else:
            raise RuntimeError("Modifying the object id is not allowed")

        super(_NumpyArrayFedObject, self).__setattr__(name, value)




class Reach(_NumpyArrayFedObject):

    def __init__(self, rivernetwork, shape, data):
        _NumpyArrayFedObject.__init__(self, rivernetwork, data)
        self.rivernetwork = rivernetwork
        self.shape = shape

    def get_downstream_reach(self):
        # doit trouver le parent dans rivernetwork
        list_iddown = self.rivernetwork._numpyarraylinks[self.rivernetwork._numpyarraylinks[self.rivernetwork.reaches_linkfieldup] == self.id][
            self.rivernetwork.reaches_linkfielddown]
        if len(list_iddown)>0:
            return self.rivernetwork._reaches[self.rivernetwork._reaches['id'] == list_iddown[0]]['object'][0]
        else:
            return None

    def get_uptream_reaches(self):
        #   Générateur de Reach
        list_idup = self.rivernetwork._numpyarraylinks[self.rivernetwork._numpyarraylinks[self.rivernetwork.reaches_linkfielddown] == self.id][
            self.rivernetwork.reaches_linkfieldup]
        for id in list_idup:
            yield self.rivernetwork._reaches[self.rivernetwork._reaches['id'] == id]['object'][0]


    def is_downstream_end(self):
        # retour de la méthode : booléen
        return self.get_downstream_reach() == None

    def is_upstream_end(self):
        # retour de la méthode : booléen
        return len(list(self.get_uptream_reaches())) == 0

    def __str__(self):
        return str(self.id)

    def _recursiveprint(self, prefix):
        string = prefix + str(self) + "\n"
        for child in self.get_uptream_reaches():
            string += child.__recursiveprint(prefix + "- ")
        return string

    def browse_points(self, collection, orientation="DOWN_TO_UP", stopper=BrowsingStopper()):
        #   Générateur de DataPoint
        if stopper.break_generator:
            return
        if orientation == "DOWN_TO_UP":
            sortedlist = np.sort(collection._numpyarray[collection._numpyarray[collection.dict_attr_fields['reach_id']] == self.id], order=collection.dict_attr_fields['dist'])
        else:
            sortedlist = np.sort(
                collection._numpyarray[collection._numpyarray[collection.dict_attr_fields['reach_id']] == self.id],
                order=collection.dict_attr_fields['dist'])
            sortedlist=np.flipud(sortedlist)
        for id in sortedlist[collection.dict_attr_fields['id']]:
           yield collection._points[collection._points['id'] == id]['object'][0]

    def get_last_point(self, collection):
        sortedlist = np.sort(
            collection._numpyarray[collection._numpyarray[collection.dict_attr_fields['reach_id']] == self.id],
            order=collection.dict_attr_fields['dist'])
        if len(sortedlist) > 0:
            lastid = sortedlist[collection.dict_attr_fields['id']][-1]
            return collection._points[collection._points['id'] == lastid]['object'][0]
        else:
            return None

    def get_first_point(self, collection):
        sortedlist = np.sort(
            collection._numpyarray[collection._numpyarray[collection.dict_attr_fields['reach_id']] == self.id], order=collection.dict_attr_fields['dist'])

        if len(sortedlist) > 0:
            firstid = sortedlist[collection.dict_attr_fields['id']][0]
            return collection._points[collection._points['id'] == firstid]['object'][0]
        else:
            return None

    def get_point(self, distance, collection, tolerance = 0.01):
        pt_list = collection._numpyarray[collection._numpyarray[collection.dict_attr_fields['reach_id']] == self.id]
        for pt_dist in pt_list[collection.dict_attr_fields['dist']]:
            if abs(pt_dist - distance) < tolerance:
                id = pt_list[pt_list[collection.dict_attr_fields['dist']] == pt_dist][collection.dict_attr_fields['id']][0]
                return collection._points[collection._points['id'] == id]['object'][0]
        return None

    def add_point(self, distance, collection):

        #Find the max currently used id in the collection, and add 1
        newid = np.max(collection._numpyarray[collection.dict_attr_fields['id']]) + 1
        #Add a row in the two numpy arrays
        to_add = np.empty(1, dtype=collection._numpyarray.dtype)
        to_add[collection.dict_attr_fields['id']] = newid
        to_add[collection.dict_attr_fields['reach_id']] = self.id
        to_add[collection.dict_attr_fields['dist']] = distance
        collection._numpyarray = np.append(collection._numpyarray, to_add)
        datapoint = DataPoint(collection, self, to_add)
        to_add = np.array([(newid, datapoint)], dtype=collection._points.dtype)
        collection._points = np.append(collection._points, to_add)

        return datapoint

    def is_upstream(self, reach):
        found = False
        for upreaches in self.get_uptream_reaches():
            found = found or upreaches.__recurs_is_upstream(reach, found)
        return found

    def __recurs_is_upstream(self, reach, found):
        found = found or self.id==reach.id
        for upreaches in self.get_uptream_reaches():
            found = found or upreaches.__recurs_is_upstream(reach, found)
        return found

    def is_downstream(self, reach):
        found = False
        downreach = self.get_downstream_reach()
        if downreach is not None:
            found = found or downreach.__recurs_is_downstream(reach, found)
        return found

    def __recurs_is_downstream(self, reach, found):
        found = found or self.id == reach.id
        downreach = self.get_downstream_reach()
        if downreach is not None:
            found = found or downreach.__recurs_is_downstream(reach, found)
        return found



class Points_collection(_NumpyArrayHolder):

    dict_attr_fields = {"id": "id",
                       "reach_id": "RID",
                       "dist": "MEAS"
                        }

    def __init__(self, rivernetwork, name):
        _NumpyArrayHolder.__init__(self)
        self.dict_attr_fields = Points_collection.dict_attr_fields.copy()
        self.name = name
        self.rivernetwork = rivernetwork
        rivernetwork.points_collection[name]=self
        self._numpyarray = np.empty(0, dtype=[(self.dict_attr_fields['id'], 'i4'),
                                              (self.dict_attr_fields['reach_id'], 'i4'),
                                              (self.dict_attr_fields['dist'], 'f8')])
        self._points = np.empty(0, dtype=[('id', 'i4'), ('object', 'O')])

    def load_table(self, points_table):

        # matrice de base
        self._numpyarray = arcpy.da.TableToNumPyArray(points_table, list(self.dict_attr_fields.values()),
                                                      null_value=-9999)
        # matrice contenant les instances de DataPoint
        self._points = np.empty(self._numpyarray.shape[0], dtype=[('id', 'i4'), ('object', 'O')])
        i = 0
        for row in self._numpyarray:
            self._points[i]['id'] = row[self.dict_attr_fields['id']]
            reachid = row[self.dict_attr_fields['reach_id']]
            try:
                reach = self.rivernetwork._reaches[self.rivernetwork._reaches['id'] == reachid]['object'][0]
            except IndexError as e:
                print(reachid)
                raise e
            self._points[i]['object'] = DataPoint(self, reach, row)
            i += 1

    def delete_point(self, datapoint):
        self._points = self._points[self._numpyarray[self.dict_attr_fields['id']] != datapoint.id]
        self._numpyarray = self._numpyarray[self._numpyarray[self.dict_attr_fields['id']] != datapoint.id]



    def save_points(self, target_table, dict_attr_output_fields=None):
        # sauvegarde les points dans une nouvelle table
        if arcpy.Exists(target_table) and arcpy.env.overwriteOutput == True:
            arcpy.Delete_management(target_table)

        # Below solution works, but too slow
        # Cursors can't be used. Solution could be to create and populate a numpy array

        # arcpy.CreateTable_management(os.path.dirname(target_table), os.path.basename(target_table))
        #
        # listfields = []
        # for attribute, addfield_params in dict_attr_fields.items():
        #     listfields.append(addfield_params[0])
        #     if addfield_params[1] == "TEXT":
        #         arcpy.AddField_management(target_table, addfield_params[0], addfield_params[1],
        #                                   field_length=addfield_params[2])
        #     else:
        #         arcpy.AddField_management(target_table, addfield_params[0], addfield_params[1])
        # pointcursor = arcpy.da.InsertCursor(target_table, listfields)
        #
        # for point in self._dict_points_collection[points_collection_name]._points['object']:
        #     datalist = []
        #     for attribute, addfield_params in dict_attr_fields.items():
        #         datalist.append(getattr(point, attribute))
        #     pointcursor.insertRow(datalist)

        # Gather metadata for the new array
        newdtype = []
        idfield = None
        if dict_attr_output_fields is None:
            # Save all fields of the original file
            dict_attr_output_fields = self.dict_attr_fields.copy()
            # and add all created attributes
            for attr in self._variablesset:
                dict_attr_output_fields[attr] = self._variablestype[attr][1]

        for attr, field in dict_attr_output_fields.items():
            if attr in self.dict_attr_fields.keys():
                # the data is in the _numpyarray, we can get its dtype
                newdtype.append((str(field), self._numpyarray.dtype.fields[self.dict_attr_fields[attr]][0]))
            else:
                # the data must be an attribute of the DataPoint
                if self._variablestype[attr][0] == "int":
                    newdtype.append((self._variablestype[attr][1], 'i4'))
                elif self._variablestype[attr][0] == "float":
                    newdtype.append((self._variablestype[attr][1], 'f8'))
                elif self._variablestype[attr][0] == "str":
                    newdtype.append((self._variablestype[attr][1], 'U'+str(self._variablestype[attr][2])))
            if attr == "id":
                idfield = field
        if idfield is None:
            raise RuntimeError("'id' field is required")

        # Create a new array
        newarray = np.empty(self._numpyarray.shape[0], dtype=newdtype)

        # Populate the array
        required_attr = []

        for field, value in dict_attr_output_fields.items():
            if field in self.dict_attr_fields.keys():
                # if the data is in the _numpyarray, than we just need to copy it
                newarray[value] = self._numpyarray[self.dict_attr_fields[field]]
            else:
                required_attr.append((field, value))

        # we need to browse the data point object for accessing the remaining data
        for row in newarray:
            dataobj = self._points[self._points['id'] == row[dict_attr_output_fields['id']]][0]
            for attribute in required_attr:
                row[attribute[1]] = getattr(dataobj['object'], attribute[0])
        #works too, but slower:
        #for row in collection._points:
        #    for attribute in required_attr:
        #        newarray[attribute[1]][newarray[idfield] == row['id']] = getattr(row['object'], attribute[0])

        # saving
        arcpy.da.NumPyArrayToTable(newarray, target_table)
        #arcpy.da.NumPyArrayToTable(newarray[0], target_table)




class DataPoint(_NumpyArrayFedObject):
    def __init__(self, pointscollection, reach, data):
        _NumpyArrayFedObject.__init__(self, pointscollection, data)
        self.points_collection = pointscollection
        self.reach = reach

