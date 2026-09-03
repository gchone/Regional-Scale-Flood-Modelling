
import os

from qgis.core import (
    QgsCoordinateTransformContext,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsPointXY,
    QgsRectangle,
    QgsSpatialIndex,
    QgsVectorFileWriter,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QMetaType

# Object returned for each line of an attribute table, by read_attribute_table
class attribute_table_line(object):
    # Simple adapter of the object return by the getFeatures()
    def __init__(self, line):
        self.line = line
    def get_field_value(self, field_name):
        return self.line[field_name]
    def get_shape(self):
        return self.line.geometry()
    def get_oid(self):
        try:
            return self.line['id']
        except Exception:
            return self.line.id()

# Read an attribute table
def read_attribute_table(vector_layer, field_names):
    # Simple adapter of the getFeatures() function♦
    for line in vector_layer.getFeatures():
        line_obj = attribute_table_line(line)
        yield line_obj


def load_table_rows(layer, field_names):
    for feature in layer.getFeatures():
        yield {field_name: feature[field_name] for field_name in field_names}


def load_line_features(layer, field_names):
    from RiverNetworkTools import Coordinate, LineFeature

    for feature in layer.getFeatures():
        geom = feature.geometry()
        if geom is None or geom.isEmpty():
            continue
        if geom.isMultipart():
            parts = geom.asMultiPolyline()
            line = parts[0] if parts else []
        else:
            line = geom.asPolyline()
        if not line:
            continue
        attrs = {field_name: feature[field_name] for field_name in field_names}
        vertices = []
        for point in line:
            m_value = None
            if hasattr(point, "m"):
                try:
                    m_value = float(point.m())
                except (TypeError, ValueError):
                    m_value = None
            vertices.append(Coordinate(float(point.x()), float(point.y()), m_value))
        yield LineFeature(attrs, vertices)


def load_point_features(layer, field_names):
    from RiverNetworkTools import Coordinate, PointFeature

    for feature in layer.getFeatures():
        geom = feature.geometry()
        if geom is None or geom.isEmpty():
            continue
        point = geom.asPoint()
        attrs = {field_name: feature[field_name] for field_name in field_names}
        yield PointFeature(attrs, Coordinate(float(point.x()), float(point.y())))


def read_point_dataset(vector_layer, field_names=None):
    available_fields = vector_layer.fields()
    available_field_names = available_fields.names()

    if field_names is None or len(field_names) == 0:
        selected_field_names = available_field_names
    else:
        selected_field_names = list(field_names)
        missing_fields = [field_name for field_name in selected_field_names if field_name not in available_field_names]
        if len(missing_fields) != 0:
            raise ValueError(f"Field(s) not found in '{vector_layer.name()}': {missing_fields}")

    field_definitions = {}
    for field_name in selected_field_names:
        field_index = available_fields.indexFromName(field_name)
        if field_index < 0:
            raise ValueError(f"Field '{field_name}' not found in '{vector_layer.name()}'.")
        field_definitions[field_name] = available_fields[field_index]

    records = []
    for feature in vector_layer.getFeatures():
        point = feature.geometry().asPoint()
        record = {
            "X": point.x(),
            "Y": point.y(),
            "_oid": feature.id(),
        }
        for field_name in selected_field_names:
            record[field_name] = feature[field_name]
        records.append(record)

    return {
        "records": records,
        "field_names": selected_field_names,
        "field_definitions": field_definitions,
        "spatial_reference": vector_layer.crs(),
    }


def read_route_geometries(vector_layer, rid_field):
    route_geometries = {}

    for feature in vector_layer.getFeatures():
        rid = feature[rid_field]
        geometry = feature.geometry()
        if geometry.isMultipart():
            parts = geometry.asMultiPolyline()
        else:
            parts = [geometry.asPolyline()]

        coordinates_parts = []
        for part in parts:
            coordinates = [(point.x(), point.y()) for point in part]
            if len(coordinates) != 0:
                coordinates_parts.append(coordinates)

        if rid not in route_geometries:
            route_geometries[rid] = []
        route_geometries[rid].extend(coordinates_parts)

    return route_geometries


def write_output_points(output_path, records, target_info, data_info, data_fields_to_keep, include_near_dist):
    fields = QgsFields()
    used_field_names = set()

    for field_name in target_info["field_names"]:
        if field_name in used_field_names:
            continue
        fields.append(QgsField(target_info["field_definitions"][field_name]))
        used_field_names.add(field_name)

    for field_name in data_fields_to_keep:
        if field_name in used_field_names:
            continue
        field_definition = data_info["field_definitions"].get(field_name)
        if field_definition is None:
            fields.append(QgsField(field_name, QMetaType.Double))
        else:
            fields.append(QgsField(field_definition))
        used_field_names.add(field_name)

    if include_near_dist and "NEAR_DIST" not in used_field_names:
        fields.append(QgsField("NEAR_DIST", QMetaType.Double))

    output_base_path, layer_name, driver_name = _resolve_output_destination(output_path)
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = driver_name
    if layer_name is not None:
        options.layerName = layer_name
        options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
    else:
        options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile

    writer = QgsVectorFileWriter.create(
        output_base_path,
        fields,
        QgsWkbTypes.Point,
        target_info.get("spatial_reference"),
        QgsCoordinateTransformContext(),
        options,
    )
    if writer is None:
        raise ValueError(f"Could not create '{output_path}'.")

    output_field_names = [field.name() for field in fields]
    for record in records:
        feature = QgsFeature(fields)
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(record.get("X"), record.get("Y"))))
        feature.setAttributes([record.get(field_name) for field_name in output_field_names])
        writer.addFeature(feature)

    del writer
    return output_path


def _resolve_output_destination(output_path):
    output_path = str(output_path)
    output_base_path = output_path
    layer_name = None

    if "|layername=" in output_path:
        output_base_path, layer_name = output_path.split("|layername=", 1)

    lower_path = output_base_path.lower()
    if lower_path.endswith(".shp"):
        driver_name = "ESRI Shapefile"
    elif lower_path.endswith(".geojson"):
        driver_name = "GeoJSON"
    else:
        driver_name = "GPKG"

    if driver_name == "GPKG" and layer_name is None:
        layer_name = os.path.splitext(os.path.basename(output_base_path))[0]

    return output_base_path, layer_name, driver_name


def read_table_dataset(vector_layer, field_names=None):
    available_fields = vector_layer.fields()
    available_field_names = available_fields.names()

    if field_names is None or len(field_names) == 0:
        selected_field_names = available_field_names
    else:
        selected_field_names = list(field_names)
        missing_fields = [field_name for field_name in selected_field_names if field_name not in available_field_names]
        if len(missing_fields) != 0:
            raise ValueError(f"Field(s) not found in '{vector_layer.name()}': {missing_fields}")

    field_definitions = {}
    for field_name in selected_field_names:
        field_index = available_fields.indexFromName(field_name)
        if field_index < 0:
            raise ValueError(f"Field '{field_name}' not found in '{vector_layer.name()}'.")
        field_definitions[field_name] = available_fields[field_index]

    records = []
    for feature in vector_layer.getFeatures():
        records.append({field_name: feature[field_name] for field_name in selected_field_names})

    return {
        "records": records,
        "field_names": selected_field_names,
        "field_definitions": field_definitions,
    }


def copy_field_via_relate_table(
    target_dataset,
    target_key_field,
    relate_table,
    relate_target_field,
    relate_source_field,
    source_dataset,
    source_key_field,
    source_value_field,
    output_field,
    output_field_dtype="float",
):
    target_layer = open_vector_dataset(target_dataset)
    source_info = read_table_dataset(source_dataset, [source_key_field, source_value_field])
    source_values = {
        row[source_key_field]: row.get(source_value_field)
        for row in source_info["records"]
        if row.get(source_key_field) not in [None, ""]
    }

    relate_info = read_table_dataset(relate_table, [relate_target_field, relate_source_field])
    target_to_source = {}
    for row in relate_info["records"]:
        target_value = row.get(relate_target_field)
        source_value = row.get(relate_source_field)
        if target_value in [None, ""] or source_value in [None, ""]:
            continue
        if target_value not in target_to_source:
            target_to_source[target_value] = source_value

    started_edit = False
    try:
        if not target_layer.isEditable():
            if not target_layer.startEditing():
                raise ValueError(f"Could not start editing '{_get_source_name(target_layer)}'.")
            started_edit = True

        output_index = target_layer.fields().indexFromName(output_field)
        if output_index < 0:
            source_field_definition = source_info["field_definitions"].get(source_value_field)
            if source_field_definition is not None:
                new_field = QgsField(source_field_definition)
                new_field.setName(output_field)
            else:
                new_field = _create_simple_qgis_field({"name": output_field, "dtype": output_field_dtype})
            if not target_layer.addAttribute(new_field):
                raise ValueError(f"Could not add field '{output_field}' to '{_get_source_name(target_layer)}'.")
            target_layer.updateFields()
            output_index = target_layer.fields().indexFromName(output_field)

        target_key_index = target_layer.fields().indexFromName(target_key_field)
        if target_key_index < 0:
            raise ValueError(f"Field '{target_key_field}' not found in '{_get_source_name(target_layer)}'.")

        for feature in target_layer.getFeatures():
            target_key = feature[target_key_index]
            source_key = target_to_source.get(target_key)
            if not target_layer.changeAttributeValue(
                feature.id(),
                output_index,
                None if source_key is None else source_values.get(source_key),
            ):
                raise ValueError(f"Could not update feature {feature.id()} in '{_get_source_name(target_layer)}'.")

        if started_edit and not target_layer.commitChanges():
            raise ValueError("; ".join(target_layer.commitErrors()) or f"Could not save '{_get_source_name(target_layer)}'.")
    except Exception:
        if started_edit and target_layer.isEditable():
            target_layer.rollBack()
        raise

    return target_dataset


def get_spatial_reference(vector_layer):
    try:
        return vector_layer.crs()
    except Exception:
        return None


def write_bed_assessment_points(output_path, rows, input_info, extra_fields, spatial_reference=None):
    fields = QgsFields()
    output_field_names = []
    used_field_names = set()

    for field_name in input_info["field_names"]:
        if field_name in used_field_names:
            continue
        field_definition = input_info["field_definitions"].get(field_name)
        if field_definition is None:
            continue
        fields.append(QgsField(field_definition))
        output_field_names.append(field_name)
        used_field_names.add(field_name)

    for field_info in extra_fields:
        field_name = field_info["name"]
        if field_name in used_field_names:
            continue
        fields.append(_create_simple_qgis_field(field_info))
        output_field_names.append(field_name)
        used_field_names.add(field_name)

    output_base_path, layer_name, driver_name = _resolve_output_destination(output_path)
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = driver_name
    if layer_name is not None:
        options.layerName = layer_name
        options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
    else:
        options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile

    writer = QgsVectorFileWriter.create(
        output_base_path,
        fields,
        QgsWkbTypes.Point,
        spatial_reference,
        QgsCoordinateTransformContext(),
        options,
    )
    if writer is None:
        raise ValueError(f"Could not create '{output_path}'.")

    for row in rows:
        feature = QgsFeature(fields)
        x_value = row.get("X")
        y_value = row.get("Y")
        if x_value is not None and y_value is not None:
            feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(float(x_value), float(y_value))))
        feature.setAttributes([row.get(field_name) for field_name in output_field_names])
        writer.addFeature(feature)

    del writer
    return output_path


def _create_simple_qgis_field(field_info):
    dtype = field_info["dtype"]
    if dtype == "str":
        field = QgsField(field_info["name"], QMetaType.QString)
        max_length = field_info.get("max_length")
        if max_length is not None:
            field.setLength(int(max_length))
        return field
    if dtype == "int":
        return QgsField(field_info["name"], QMetaType.Int)
    return QgsField(field_info["name"], QMetaType.Double)


def read_point_dataset_any(vector_source, field_names=None):
    available_fields = vector_source.fields()
    available_field_names = available_fields.names()

    if field_names is None or len(field_names) == 0:
        selected_field_names = available_field_names
    else:
        selected_field_names = list(field_names)
        missing_fields = [field_name for field_name in selected_field_names if field_name not in available_field_names]
        if len(missing_fields) != 0:
            source_name = _get_source_name(vector_source)
            raise ValueError(f"Field(s) not found in '{source_name}': {missing_fields}")

    field_definitions = {}
    for field_name in selected_field_names:
        field_index = available_fields.indexFromName(field_name)
        if field_index < 0:
            source_name = _get_source_name(vector_source)
            raise ValueError(f"Field '{field_name}' not found in '{source_name}'.")
        field_definitions[field_name] = available_fields[field_index]

    records = []
    for feature in vector_source.getFeatures():
        geom = feature.geometry()
        if geom is None or geom.isEmpty():
            point_x = None
            point_y = None
        else:
            point = geom.asPoint()
            point_x = point.x()
            point_y = point.y()
        record = {
            "X": point_x,
            "Y": point_y,
            "_oid": feature.id(),
        }
        for field_name in selected_field_names:
            record[field_name] = feature[field_name]
        records.append(record)

    return {
        "records": records,
        "field_names": selected_field_names,
        "field_definitions": field_definitions,
        "spatial_reference": _get_source_crs(vector_source),
    }


def write_output_table(output_path, rows, input_info, extra_fields):
    fields = QgsFields()
    output_field_names = []
    used_field_names = set()

    for field_name in input_info["field_names"]:
        field_key = str(field_name).lower()
        if field_key in used_field_names:
            continue
        field_definition = input_info["field_definitions"].get(field_name)
        if field_definition is None:
            continue
        fields.append(QgsField(field_definition))
        output_field_names.append(field_name)
        used_field_names.add(field_key)

    for field_info in extra_fields:
        field_name = field_info["name"]
        field_key = str(field_name).lower()
        if field_key in used_field_names:
            continue
        field_definition = field_info.get("field_definition")
        if field_definition is not None:
            field = QgsField(field_definition)
            field.setName(field_name)
        else:
            field = _create_simple_qgis_field(field_info)
        fields.append(field)
        output_field_names.append(field_name)
        used_field_names.add(field_key)

    output_base_path, layer_name, driver_name = _resolve_output_destination(output_path)
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = driver_name
    if layer_name is not None:
        options.layerName = layer_name
        options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
    else:
        options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile

    writer = QgsVectorFileWriter.create(
        output_base_path,
        fields,
        QgsWkbTypes.NoGeometry,
        input_info.get("spatial_reference"),
        QgsCoordinateTransformContext(),
        options,
    )
    if writer is None:
        raise ValueError(f"Could not create '{output_path}'.")

    for row in rows:
        feature = QgsFeature(fields)
        feature.setAttributes([row.get(field_name) for field_name in output_field_names])
        writer.addFeature(feature)

    del writer
    return output_path


def _get_source_name(vector_source):
    if hasattr(vector_source, "name"):
        try:
            return vector_source.name()
        except Exception:
            pass
    return str(vector_source)


def _get_source_crs(vector_source):
    if hasattr(vector_source, "crs"):
        try:
            return vector_source.crs()
        except Exception:
            pass
    if hasattr(vector_source, "sourceCrs"):
        try:
            return vector_source.sourceCrs()
        except Exception:
            pass
    return None


def open_vector_dataset(dataset, layer_name=None):
    if hasattr(dataset, "getFeatures"):
        return dataset

    dataset_path = str(dataset)
    if layer_name not in [None, ""] and "|layername=" not in dataset_path and dataset_path.lower().endswith(".gpkg"):
        dataset_path = dataset_path + "|layername=" + str(layer_name)

    label = layer_name
    if label in [None, ""]:
        label = os.path.splitext(os.path.basename(str(dataset)))[0]

    layer = QgsVectorLayer(dataset_path, str(label), "ogr")
    if not layer.isValid():
        raise ValueError(f"Could not load '{dataset_path}'.")
    return layer


def read_table_dataset_with_oid(vector_source, field_names=None):
    available_fields = vector_source.fields()
    available_field_names = available_fields.names()

    if field_names is None or len(field_names) == 0:
        selected_field_names = available_field_names
    else:
        selected_field_names = list(field_names)
        missing_fields = [field_name for field_name in selected_field_names if field_name not in available_field_names]
        if len(missing_fields) != 0:
            source_name = _get_source_name(vector_source)
            raise ValueError(f"Field(s) not found in '{source_name}': {missing_fields}")

    field_definitions = {}
    for field_name in selected_field_names:
        field_index = available_fields.indexFromName(field_name)
        if field_index < 0:
            source_name = _get_source_name(vector_source)
            raise ValueError(f"Field '{field_name}' not found in '{source_name}'.")
        field_definitions[field_name] = available_fields[field_index]

    records = []
    for feature in vector_source.getFeatures():
        record = {"_oid": feature.id()}
        for field_name in selected_field_names:
            record[field_name] = feature[field_name]
        records.append(record)

    return {
        "records": records,
        "field_names": selected_field_names,
        "field_definitions": field_definitions,
    }


def read_feature_extents(vector_source, field_names=None):
    available_fields = vector_source.fields()
    available_field_names = available_fields.names()

    if field_names is None or len(field_names) == 0:
        selected_field_names = available_field_names
    else:
        selected_field_names = list(field_names)
        missing_fields = [field_name for field_name in selected_field_names if field_name not in available_field_names]
        if len(missing_fields) != 0:
            source_name = _get_source_name(vector_source)
            raise ValueError(f"Field(s) not found in '{source_name}': {missing_fields}")

    field_definitions = {}
    for field_name in selected_field_names:
        field_index = available_fields.indexFromName(field_name)
        if field_index < 0:
            source_name = _get_source_name(vector_source)
            raise ValueError(f"Field '{field_name}' not found in '{source_name}'.")
        field_definitions[field_name] = available_fields[field_index]

    records = []
    for feature in vector_source.getFeatures():
        extent = feature.geometry().boundingBox()
        record = {
            "_oid": feature.id(),
            "XMin": extent.xMinimum(),
            "YMin": extent.yMinimum(),
            "XMax": extent.xMaximum(),
            "YMax": extent.yMaximum(),
        }
        for field_name in selected_field_names:
            record[field_name] = feature[field_name]
        records.append(record)

    return {
        "records": records,
        "field_names": selected_field_names,
        "field_definitions": field_definitions,
    }


class _PolygonLookup:
    def __init__(self, vector_source):
        self.records = {}
        features = list(vector_source.getFeatures())
        self.index = QgsSpatialIndex(features)

        for feature in features:
            geometry = feature.geometry()
            if geometry is None or geometry.isEmpty():
                continue
            bbox = geometry.boundingBox()
            self.records[feature.id()] = {
                "_oid": feature.id(),
                "geometry": geometry,
                "XMin": float(bbox.xMinimum()),
                "YMin": float(bbox.yMinimum()),
                "XMax": float(bbox.xMaximum()),
                "YMax": float(bbox.yMaximum()),
            }

    def find_containing_feature(self, x_value, y_value):
        point_geometry = QgsGeometry.fromPointXY(QgsPointXY(float(x_value), float(y_value)))
        for feature_id in self.index.intersects(point_geometry.boundingBox()):
            record = self.records.get(feature_id)
            if record is None:
                continue
            if record["geometry"].contains(point_geometry):
                return record
        return None


def build_polygon_lookup(vector_source):
    return _PolygonLookup(vector_source)


def write_tiling_polygons(output_folder, records, spatial_reference=None):
    output_path = os.path.join(output_folder, "polyzones.gpkg")
    fields = QgsFields()
    fields.append(QgsField("GRID_CODE", QMetaType.Int))
    fields.append(QgsField("Lake_ID", QMetaType.Int))

    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = "polyzones"
    options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile

    writer = QgsVectorFileWriter.create(
        output_path,
        fields,
        QgsWkbTypes.Polygon,
        spatial_reference,
        QgsCoordinateTransformContext(),
        options,
    )
    if writer is None:
        raise ValueError(f"Could not create '{output_path}'.")

    for record in records:
        feature = QgsFeature(fields)
        feature.setGeometry(QgsGeometry.fromRect(QgsRectangle(
            float(record["XMin"]),
            float(record["YMin"]),
            float(record["XMax"]),
            float(record["YMax"]),
        )))
        feature.setAttributes([int(record["GRID_CODE"]), int(record["Lake_ID"])])
        writer.addFeature(feature)

    del writer
    return output_path


def write_tiling_source_points(output_folder, records, spatial_reference=None):
    output_path = os.path.join(output_folder, "sourcepoints.gpkg")
    fields = QgsFields()
    fields.append(QgsField("ZoneID", QMetaType.Int))
    fields.append(QgsField("fpid", QMetaType.Int))

    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = "sourcepoints"
    options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile

    writer = QgsVectorFileWriter.create(
        output_path,
        fields,
        QgsWkbTypes.Point,
        spatial_reference,
        QgsCoordinateTransformContext(),
        options,
    )
    if writer is None:
        raise ValueError(f"Could not create '{output_path}'.")

    for record in records:
        feature = QgsFeature(fields)
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(float(record["X"]), float(record["Y"]))))
        feature.setAttributes([int(record["ZoneID"]), int(record["fpid"])])
        writer.addFeature(feature)

    del writer
    return output_path


def write_hydraulic_envelopezones(output_folder, records, spatial_reference=None):
    output_path = os.path.join(output_folder, "envelopezones.gpkg")
    fields = QgsFields()
    fields.append(QgsField("GRID_CODE", QMetaType.Int))
    fields.append(QgsField("Lake_ID", QMetaType.Int))

    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = "envelopezones"
    options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile

    writer = QgsVectorFileWriter.create(
        output_path,
        fields,
        QgsWkbTypes.Polygon,
        spatial_reference,
        QgsCoordinateTransformContext(),
        options,
    )
    if writer is None:
        raise ValueError(f"Could not create '{output_path}'.")

    for record in records:
        feature = QgsFeature(fields)
        feature.setGeometry(QgsGeometry.fromRect(QgsRectangle(
            float(record["XMin"]),
            float(record["YMin"]),
            float(record["XMax"]),
            float(record["YMax"]),
        )))
        feature.setAttributes([int(record["GRID_CODE"]), int(record["Lake_ID"])])
        writer.addFeature(feature)

    del writer
    return output_path


def write_hydraulic_inbci(output_folder, records, spatial_reference=None):
    output_path = os.path.join(output_folder, "inbci.gpkg")
    fields = QgsFields()
    fields.append(QgsField("zoneid", QMetaType.Int))
    fields.append(QgsField("flowacc", QMetaType.Double))
    fields.append(QgsField("type", QMetaType.QString))
    fields.append(QgsField("fpid", QMetaType.Int))

    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = "inbci"
    options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile

    writer = QgsVectorFileWriter.create(
        output_path,
        fields,
        QgsWkbTypes.Point,
        spatial_reference,
        QgsCoordinateTransformContext(),
        options,
    )
    if writer is None:
        raise ValueError(f"Could not create '{output_path}'.")

    for record in records:
        feature = QgsFeature(fields)
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(float(record["X"]), float(record["Y"]))))
        feature.setAttributes([
            int(record["zoneid"]),
            float(record["flowacc"]),
            record["type"],
            int(record["fpid"]),
        ])
        writer.addFeature(feature)

    del writer
    return output_path


def write_hydraulic_outbci(output_folder, records, spatial_reference=None):
    output_path = os.path.join(output_folder, "outbci.gpkg")
    fields = QgsFields()
    fields.append(QgsField("zoneid", QMetaType.Int))
    fields.append(QgsField("side", QMetaType.QString))

    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = "outbci"
    options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile

    writer = QgsVectorFileWriter.create(
        output_path,
        fields,
        QgsWkbTypes.Point,
        spatial_reference,
        QgsCoordinateTransformContext(),
        options,
    )
    if writer is None:
        raise ValueError(f"Could not create '{output_path}'.")

    for record in records:
        feature = QgsFeature(fields)
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(float(record["X"]), float(record["Y"]))))
        feature.setAttributes([int(record["zoneid"]), record["side"]])
        writer.addFeature(feature)

    del writer
    return output_path


def write_point_features(output_path, features, input_info=None, extra_fields=None, spatial_reference=None):
    from RiverNetworkTools import ensure_point_feature

    if input_info is None:
        input_info = {"field_names": [], "field_definitions": {}}
    if extra_fields is None:
        extra_fields = []

    fields, output_field_names = _build_output_feature_fields(input_info, extra_fields)
    output_base_path, layer_name, driver_name = _resolve_output_destination(output_path)
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = driver_name
    if layer_name is not None:
        options.layerName = layer_name
        options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
    else:
        options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile

    writer = QgsVectorFileWriter.create(
        output_base_path,
        fields,
        QgsWkbTypes.Point,
        spatial_reference,
        QgsCoordinateTransformContext(),
        options,
    )
    if writer is None:
        raise ValueError(f"Could not create '{output_path}'.")

    for raw_feature in features:
        feature = ensure_point_feature(raw_feature)
        qgs_feature = QgsFeature(fields)
        qgs_feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(float(feature.point.x), float(feature.point.y))))
        qgs_feature.setAttributes([feature.attributes.get(field_name) for field_name in output_field_names])
        writer.addFeature(qgs_feature)

    del writer
    return output_path


def write_line_features(output_path, features, input_info=None, extra_fields=None, spatial_reference=None, has_m=False):
    from RiverNetworkTools import ensure_line_feature
    from qgis.core import QgsLineString, QgsPoint

    if input_info is None:
        input_info = {"field_names": [], "field_definitions": {}}
    if extra_fields is None:
        extra_fields = []

    fields, output_field_names = _build_output_feature_fields(input_info, extra_fields)
    output_base_path, layer_name, driver_name = _resolve_output_destination(output_path)
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = driver_name
    if layer_name is not None:
        options.layerName = layer_name
        options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
    else:
        options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile

    writer = QgsVectorFileWriter.create(
        output_base_path,
        fields,
        QgsWkbTypes.LineStringM if has_m else QgsWkbTypes.LineString,
        spatial_reference,
        QgsCoordinateTransformContext(),
        options,
    )
    if writer is None:
        raise ValueError(f"Could not create '{output_path}'.")

    for raw_feature in features:
        feature = ensure_line_feature(raw_feature)
        qgs_feature = QgsFeature(fields)
        if has_m:
            geometry_points = [
                QgsPoint(float(vertex.x), float(vertex.y), m=0.0 if vertex.m is None else float(vertex.m))
                for vertex in feature.vertices
            ]
            qgs_feature.setGeometry(QgsGeometry(QgsLineString(geometry_points)))
        else:
            qgs_feature.setGeometry(
                QgsGeometry.fromPolylineXY(
                    [QgsPointXY(float(vertex.x), float(vertex.y)) for vertex in feature.vertices]
                )
            )
        qgs_feature.setAttributes([feature.attributes.get(field_name) for field_name in output_field_names])
        writer.addFeature(qgs_feature)

    del writer
    return output_path


def _build_output_feature_fields(input_info, extra_fields):
    fields = QgsFields()
    output_field_names = []
    used_field_names = set()

    for field_name in input_info["field_names"]:
        field_key = str(field_name).lower()
        if field_key in used_field_names:
            continue
        field_definition = input_info["field_definitions"].get(field_name)
        if field_definition is None:
            continue
        fields.append(QgsField(field_definition))
        output_field_names.append(field_name)
        used_field_names.add(field_key)

    for field_info in extra_fields:
        field_name = field_info["name"]
        field_key = str(field_name).lower()
        if field_key in used_field_names:
            continue
        field_definition = field_info.get("field_definition")
        if field_definition is not None:
            field = QgsField(field_definition)
            field.setName(field_name)
        else:
            field = _create_simple_qgis_field(field_info)
        fields.append(field)
        output_field_names.append(field_name)
        used_field_names.add(field_key)

    return fields, output_field_names
