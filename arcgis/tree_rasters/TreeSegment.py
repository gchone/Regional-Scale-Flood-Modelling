# coding: latin-1

# Fichier TreeSegment.py
# v0.0.2 - 24/10/2017

### Contenu ###
# classe TreeSegment : Classe abstraite de gestion générique d'un segment d'un arbre

### Historique des versions ###
# v0.0.1 - 18/09/2017 - Création
# v0.0.2 - 24/10/2017 - Description modifiée - Guénolé Choné



class TreeSegment(object):

    def __init__(self, id):
        #   id : int - identifiant du segment
        self.__children = []
        self.id = id
        self.__parent = None

    def get_parent(self):
        #   retour de la méthode : TreeSegment - le segment parent (segment aval)
        return self.__parent



    def add_child(self, child):
        #   child : TreeSegment - segment à ajouter à la liste des segment amont
        self.__children.append(child)
        child.__parent = self

    def get_childrens(self):
        #   retour de la méthode : Liste de TreeSegment
        return self.__children

    def remove_child(self,child):
        self.__children.remove(child)
        child.__parent = None

    def is_root(self):
        # retour de la méthode : booléen
        return self.__parent == None

    def is_leaf(self):
        # retour de la méthode : booléen
        return len(self.get_childrens()) == 0

    def __str__(self):
        return self.__recursiveprint("")

    def __recursiveprint(self, prefix):

        string = prefix + str(self.id) + "\n"
        for child in self.get_childrens():
            string += child.__recursiveprint(prefix+"- ")
        return string




