from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterFile,
    QgsProcessingParameterField,
    QgsProcessingParameterString,
    QgsProcessingParameterFeatureSink,
    QgsField,
    QgsFeature,
    QgsVectorFileWriter,
)
from qgis.PyQt.QtCore import QVariant
import csv


class JoinFloodDischarge(QgsProcessingAlgorithm):

    STATIONS   = "STATIONS"
    NAME_FIELD = "NAME_FIELD"
    CSV_FILE   = "CSV_FILE"
    SCENARIOS  = "SCENARIOS"
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
            "columns = station names) and adds each selected scenario's discharge "
            "values as a new field on the gauging stations point layer, matched by "
            "station name.\n\n"
            "All scenarios needed should be selected in one run - each run starts "
            "fresh from the Stations input's own fields, so running this "
            "separately per scenario against the same original stations layer "
            "will not accumulate fields across runs; only the last scenario run "
            "would end up in the output.\n\n"
            "Inputs:\n"
            "- Stations: gauging station points\n"
            "- Name field: station name field on the stations layer\n"
            "- CSV file: discharge CSV (first column = scenario name)\n"
            "- Scenarios: which row(s) to use, semicolon-separated (e.g. Q100;Q200;Q350)\n\n"
            "Output: stations with each selected scenario's discharge added as its "
            "own field (e.g. Q100, Q200, Q350).\n"
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
            self.SCENARIOS, "Scenarios (semicolon-separated, e.g. Q100;Q200;Q350)",
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, "Stations with discharge",
        ))

    def processAlgorithm(self, parameters, context, feedback):
        stations   = self.parameterAsVectorLayer(parameters, self.STATIONS, context)
        name_field = self.parameterAsString(parameters, self.NAME_FIELD, context)
        csv_path   = self.parameterAsFile(parameters, self.CSV_FILE, context)
        scenarios_text = self.parameterAsString(parameters, self.SCENARIOS, context)

        if stations is None:
            raise QgsProcessingException("Stations layer is invalid")

        scenarios = [s.strip() for s in scenarios_text.split(";") if s.strip()]
        if not scenarios:
            raise QgsProcessingException("No scenario(s) provided")

        # discharge_by_station[scenario][station_name] = value
        discharge_by_station = {s: {} for s in scenarios}
        remaining = set(scenarios)

        with open(csv_path, "r") as f:
            reader = csv.reader(f)
            headers = next(reader)
            station_names = headers[1:]
            for row in reader:
                if row[0] in remaining:
                    for name, val in zip(station_names, row[1:]):
                        discharge_by_station[row[0]][name] = float(val)
                    remaining.discard(row[0])
                    if not remaining:
                        break

        if remaining:
            raise QgsProcessingException(
                f"Scenario(s) not found in {csv_path}: {sorted(remaining)}"
            )

        for scenario in scenarios:
            feedback.pushInfo(f"Found {len(discharge_by_station[scenario])} station discharge(s) for {scenario}")

        out_fields = stations.fields()
        for scenario in scenarios:
            if out_fields.indexOf(scenario) == -1:
                out_fields.append(QgsField(scenario, QVariant.Double))
            else:
                feedback.pushWarning(f"Field '{scenario}' already exists on the Stations input - overwriting its values")

        sink, dest_id = self.parameterAsSink(
            parameters, self.OUTPUT, context,
            out_fields, stations.wkbType(), stations.sourceCrs(),
        )
        if sink is None:
            raise QgsProcessingException("Could not create output sink")

        unmatched = {s: [] for s in scenarios}
        for feat in stations.getFeatures():
            name = feat[name_field]
            out_feat = QgsFeature(out_fields)
            out_feat.setGeometry(feat.geometry())

            attrs = feat.attributes()
            if len(attrs) < out_fields.count():
                # Existing feature attrs are shorter than out_fields only when
                # none of the requested scenario fields already existed on
                # the input - pad with the new scenario values in order.
                for scenario in scenarios:
                    val = discharge_by_station[scenario].get(name)
                    attrs.append(val)
                    if name not in discharge_by_station[scenario]:
                        unmatched[scenario].append(name)
            else:
                # One or more scenario fields already existed on the input -
                # set each by field index instead of assuming append order.
                for scenario in scenarios:
                    val = discharge_by_station[scenario].get(name)
                    attrs[out_fields.indexOf(scenario)] = val
                    if name not in discharge_by_station[scenario]:
                        unmatched[scenario].append(name)

            out_feat.setAttributes(attrs)
            sink.addFeature(out_feat)

        for scenario, names in unmatched.items():
            if names:
                feedback.pushWarning(f"{len(names)} station(s) had no {scenario} value: {names}")

        return {self.OUTPUT: dest_id}