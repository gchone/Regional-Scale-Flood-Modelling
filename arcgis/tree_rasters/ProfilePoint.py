# coding: latin-1

# Fichier ProfilePoint.py
# v0.0.2 - 24/10/2017

### Contenu ###
# classe ProfilePoint : Classe représentant un point du profil longitudinal

### Historique des versions ###
# v0.0.1 - 28/09/2017 - Création - Guénolé Choné
# v0.0.2 - 24/10/2017 - Description modifiée - Guénolé Choné
# v0.0.3 - 09/05/2019 - Pickle friendly - Guénolé Choné
# v0.1 - Nov 2020 - Modification de la structure pour accommoder des profiles multiples

# Structure:
# ProfilePoint a des attributs (de type "z_bed", "width", "flow_acc", etc...) s'il est de type ProfilePoint
# Il a un dictionnaire (data_dict) de __ProfilePoint_data s'il est de type ProfilePointMulti
# Les clés de data_dict sont les noms des rasters (par journée d'acquisition LiDAR), les attributs de
#  __ProfilePoint_data sont de type "z_bed", "width", "flow_acc", etc...


import collections

class ProfilePoint(object):


    def __init__(self, row, col, dist, dictdata):
        #zlidar, width, n, Q:
        #   dist : float - distance (en m) jusqu'à la section aval
        #   zbed : float - elevation du lit (en m)
        #   width : float - largeur (en m)

        for key, elem in dictdata.items():
            self.__dict__[key] = elem

        self.row = row
        self.col = col
        # dist = distance to downstream point
        self.dist=dist


class ProfilePoint_data(object):
    def __init__(self, dist, dictdata):
        self.dist = dist
        for key, elem in dictdata.items():
            self.__dict__[key] = elem



class ProfilePointMulti(ProfilePoint):

    def __init__(self, row, col, dist, dictdata):

        # zlidar, width, n, Q:
        #   dist : float - distance (en m) jusqu'à la section aval
        #   zbed : float - elevation du lit (en m)
        #   width : float - largeur (en m)

        self.data_dict = {}
        for raster_name, subdict in dictdata.items():
            # dist = distance to downstream point
            # passed to the __ProfilePoint_data, but kept in the ProfilePointMulti in read only
            self.data_dict[raster_name] = ProfilePoint_data(dist, subdict)

        self.row = row
        self.col = col

    def __setattr__(self, key, value):
        if key == "dist":
            for raster_name, PP_data in self.data_dict.items():
                PP_data.dist = value
        else:
            super(ProfilePointMulti, self).__setattr__(key, value)