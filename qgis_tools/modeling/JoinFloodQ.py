from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterFile,
    QgsProcessingParameterField,
    QgsProcessingParameterString,
    QgsProcessingParameterFeatureSink,
    QgsField,
    QgsVectorFileWriter,
)
from qgis.PyQt.QtCore import QVariant
import csv


class JoinFloodDischarge(QgsProcessingAlgorithm):

    STATIONS   = "STATIONS"
    NAME_FIELD = "NAME_FIELD"
    CSV_FILE   = "CSV_FILE"
    SCENARIO   = "SCENARIO"
    OUTPUT     = "OUTPUT"

    def name(self):
        return "joinflooddischarge"

    def displayName(self):
        return "Join flood discharge to stations"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Modeling"

    def groupId(self):
        return "concordiariverlab_floodtools_modeling"

    def createInstance(self):
        return JoinFloodDischarge()

    def shortHelpString(self):
        return (
            "Join flood discharge to stations\n\n"
            "Reads a flood discharge CSV (rows = discharge scenarios e.g. Q20/Q100, "
            "columns = station names) and adds the selected scenario's discharge "
            "values as a new field on the gauging stations point layer, matched by "
            "station name.\n\n"
            "Inputs:\n"
            "- Stations: gauging station points\n"
            "- Name field: station name field on the stations layer\n"
            "- CSV file: discharge CSV (first column = scenario name)\n"
            "- Scenario: which row to use, e.g. Q100\n\n"
            "Output: stations with the scenario's discharge added as a new field. "
            "Rerun with a different scenario for each flood return period needed.\n"
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.STATIONS, "Stations",
        ))
        self.addParameter(QgsProcessingParameterField(
            self.NAME_FIELD, "Name field", parentLayerParameterName=self.STATIONS,
        ))
        self.addParameter(QgsProcessingParameterFile(
            self.CSV_FILE, "Discharge CSV",
        ))
        self.addParameter(QgsProcessingParameterString(
            self.SCENARIO, "Scenario (e.g. Q100)",
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, "Stations with discharge",
        ))

    def processAlgorithm(self, parameters, context, feedback):
        stations   = self.parameterAsVectorLayer(parameters, self.STATIONS, context)
        name_field = self.parameterAsString(parameters, self.NAME_FIELD, context)
        csv_path   = self.parameterAsFile(parameters, self.CSV_FILE, context)
        scenario   = self.parameterAsString(parameters, self.SCENARIO, context)

        if stations is None:
            raise QgsProcessingException("Stations layer is invalid")

        discharge_by_station = {}
        with open(csv_path, "r") as f:
            reader = csv.reader(f)
            headers = next(reader)
            station_names = headers[1:]
            for row in reader:
                if row[0] == scenario:
                    for name, val in zip(station_names, row[1:]):
                        discharge_by_station[name] = float(val)
                    break
            else:
                raise QgsProcessingException(f"Scenario '{scenario}' not found in {csv_path}")

        feedback.pushInfo(f"Found {len(discharge_by_station)} station discharge(s) for {scenario}")

        out_fields = stations.fields()
        if out_fields.indexOf(scenario) == -1:
            out_fields.append(QgsField(scenario, QVariant.Double))

        sink, dest_id = self.parameterAsSink(
            parameters, self.OUTPUT, context,
            out_fields, stations.wkbType(), stations.sourceCrs(),
        )
        if sink is None:
            raise QgsProcessingException("Could not create output sink")

        unmatched = []
        for feat in stations.getFeatures():
            name = feat[name_field]
            attrs = feat.attributes()
            attrs.append(discharge_by_station.get(name))
            if name not in discharge_by_station:
                unmatched.append(name)
            from qgis.core import QgsFeature
            out_feat = QgsFeature(out_fields)
            out_feat.setGeometry(feat.geometry())
            out_feat.setAttributes(attrs)
            sink.addFeature(out_feat)

        if unmatched:
            feedback.pushWarning(f"{len(unmatched)} station(s) had no {scenario} value: {unmatched}")

        return {self.OUTPUT: dest_id}