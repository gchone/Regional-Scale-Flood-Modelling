import arcpy
import os


# Object returned for each line of an attribute table, by read_attribute_table, with methods to get field values
# by name, as well as the shape and the OID
class attribute_table_line(object):
    def __init__(self, field_names, field_values):
        self.field_names = field_names
        self.field_values = field_values
    def get_field_value(self, field_name):
        if field_name in self.field_names:
            index = self.field_names.index(field_name)
            return self.field_values[index]
        else:
            raise ValueError(f"Field '{field_name}' not found in fields_list.")
    def get_shape(self):
        return self.get_field_value("SHAPE@")
    def get_oid(self):
        return self.get_field_value("OID@")

# Read an attribute table
def read_attribute_table(str_inbci, field_names):
    # This function is based on arcpy.da.SearchCursor. However, it returns an object (an instance of attribute_table_line, above)
    # with methods to get field values by name, instead of a tuple, for a better code readability
    if "SHAPE@" not in field_names: # Add the shape field if not already included
        field_names =  field_names + ["SHAPE@"]
    if "OID@" not in field_names: # Add the ID field if not already included
        field_names = field_names + ["OID@"]
    for line in arcpy.da.SearchCursor(str_inbci, field_names):
        line_obj = attribute_table_line(field_names, line)
        yield line_obj


def load_table_rows(table, field_names):
    for row in arcpy.da.SearchCursor(table, field_names):
        yield dict(zip(field_names, row))


def load_line_features(feature_class, field_names):
    from RiverNetworkTools import Coordinate, LineFeature

    cursor_fields = list(field_names)
    if "SHAPE@" not in cursor_fields:
        cursor_fields.append("SHAPE@")
    for row in arcpy.da.SearchCursor(feature_class, cursor_fields):
        values = dict(zip(cursor_fields, row))
        shape = values.pop("SHAPE@")
        part = shape.getPart(0)
        vertices = []
        for point in part:
            if point is None:
                continue
            m_value = None
            if hasattr(point, "M"):
                try:
                    m_value = float(point.M)
                except (TypeError, ValueError):
                    m_value = None
            vertices.append(Coordinate(float(point.X), float(point.Y), m_value))
        yield LineFeature(values, vertices)


def load_point_features(feature_class, field_names):
    from RiverNetworkTools import Coordinate, PointFeature

    cursor_fields = list(field_names)
    if "SHAPE@" not in cursor_fields:
        cursor_fields.append("SHAPE@")
    for row in arcpy.da.SearchCursor(feature_class, cursor_fields):
        values = dict(zip(cursor_fields, row))
        shape = values.pop("SHAPE@")
        point = shape.firstPoint
        yield PointFeature(values, Coordinate(float(point.X), float(point.Y)))


def read_point_dataset(dataset, field_names=None):
    available_fields = [field for field in arcpy.ListFields(dataset) if field.type not in ["Geometry", "OID"]]
    available_field_names = [field.name for field in available_fields]

    if field_names is None or len(field_names) == 0:
        selected_field_names = available_field_names
    else:
        selected_field_names = list(field_names)
        missing_fields = [field_name for field_name in selected_field_names if field_name not in available_field_names]
        if len(missing_fields) != 0:
            raise ValueError(f"Field(s) not found in '{dataset}': {missing_fields}")

    field_definitions = {}
    for field in available_fields:
        if field.name in selected_field_names:
            field_definitions[field.name] = field

    cursor_fields = list(selected_field_names) + ["SHAPE@XY", "OID@"]
    records = []
    for row in arcpy.da.SearchCursor(dataset, cursor_fields):
        xy = row[len(selected_field_names)]
        record = {
            "X": None if xy is None else xy[0],
            "Y": None if xy is None else xy[1],
            "_oid": row[len(selected_field_names) + 1],
        }
        for index, field_name in enumerate(selected_field_names):
            record[field_name] = row[index]
        records.append(record)

    return {
        "records": records,
        "field_names": selected_field_names,
        "field_definitions": field_definitions,
        "spatial_reference": arcpy.Describe(dataset).spatialReference,
    }


def read_route_geometries(routes, rid_field):
    route_geometries = {}

    for rid, shape in arcpy.da.SearchCursor(routes, [rid_field, "SHAPE@"]):
        parts = []
        if shape is not None:
            for part in shape:
                coordinates = []
                for point in part:
                    if point is not None:
                        coordinates.append((point.X, point.Y))
                if len(coordinates) != 0:
                    parts.append(coordinates)
        if rid not in route_geometries:
            route_geometries[rid] = []
        route_geometries[rid].extend(parts)

    return route_geometries


def write_output_points(output_path, records, target_info, data_info, data_fields_to_keep, include_near_dist):
    output_folder = os.path.dirname(output_path)
    output_name = os.path.basename(output_path)
    if output_folder == "":
        output_folder = arcpy.env.workspace

    create_result = arcpy.management.CreateFeatureclass(
        output_folder,
        output_name,
        "POINT",
        spatial_reference=target_info.get("spatial_reference"),
    )
    output_feature_class = create_result.getOutput(0)

    output_field_names = []
    used_field_names = set()

    for field_name in target_info["field_names"]:
        if field_name in used_field_names:
            continue
        if not _add_arcgis_field(output_feature_class, target_info["field_definitions"][field_name]):
            continue
        output_field_names.append(field_name)
        used_field_names.add(field_name)

    for field_name in data_fields_to_keep:
        if field_name in used_field_names:
            continue
        field_definition = data_info["field_definitions"].get(field_name)
        if field_definition is None:
            arcpy.management.AddField(output_feature_class, field_name, "DOUBLE")
        else:
            if not _add_arcgis_field(output_feature_class, field_definition):
                continue
        output_field_names.append(field_name)
        used_field_names.add(field_name)

    if include_near_dist and "NEAR_DIST" not in used_field_names:
        arcpy.management.AddField(output_feature_class, "NEAR_DIST", "DOUBLE")
        output_field_names.append("NEAR_DIST")

    with arcpy.da.InsertCursor(output_feature_class, ["SHAPE@XY"] + output_field_names) as cursor:
        for record in records:
            row = [(record.get("X"), record.get("Y"))]
            for field_name in output_field_names:
                row.append(record.get(field_name))
            cursor.insertRow(row)

    return output_feature_class


def _add_arcgis_field(output_feature_class, field_definition):
    field_type = {
        "String": "TEXT",
        "SmallInteger": "SHORT",
        "Integer": "LONG",
        "Single": "FLOAT",
        "Double": "DOUBLE",
        "Date": "DATE",
        "GUID": "GUID",
        "GlobalID": "GUID",
    }.get(field_definition.type, None)

    if field_type is None:
        return False

    add_field_kwargs = {}
    if field_type == "TEXT" and field_definition.length not in [None, 0]:
        add_field_kwargs["field_length"] = field_definition.length
    if field_type in ["FLOAT", "DOUBLE"]:
        if field_definition.precision not in [None, 0]:
            add_field_kwargs["field_precision"] = field_definition.precision
        if field_definition.scale not in [None, 0]:
            add_field_kwargs["field_scale"] = field_definition.scale
    if field_definition.aliasName not in [None, ""]:
        add_field_kwargs["field_alias"] = field_definition.aliasName

    arcpy.management.AddField(output_feature_class, field_definition.name, field_type, **add_field_kwargs)
    return True


def read_table_dataset(dataset, field_names=None):
    available_fields = [field for field in arcpy.ListFields(dataset) if field.type not in ["Geometry", "OID"]]
    available_field_names = [field.name for field in available_fields]

    if field_names is None or len(field_names) == 0:
        selected_field_names = available_field_names
    else:
        selected_field_names = list(field_names)
        missing_fields = [field_name for field_name in selected_field_names if field_name not in available_field_names]
        if len(missing_fields) != 0:
            raise ValueError(f"Field(s) not found in '{dataset}': {missing_fields}")

    field_definitions = {}
    for field in available_fields:
        if field.name in selected_field_names:
            field_definitions[field.name] = field

    records = []
    for row in arcpy.da.SearchCursor(dataset, selected_field_names):
        records.append(dict(zip(selected_field_names, row)))

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

    existing_fields = [field.name for field in arcpy.ListFields(target_dataset)]
    if output_field not in existing_fields:
        source_field_definition = source_info["field_definitions"].get(source_value_field)
        if source_field_definition is not None:
            _add_arcgis_field_like(target_dataset, output_field, source_field_definition, output_field_dtype)
        else:
            _add_simple_arcgis_field(target_dataset, {"name": output_field, "dtype": output_field_dtype})

    with arcpy.da.UpdateCursor(target_dataset, [target_key_field, output_field]) as cursor:
        for row in cursor:
            source_key = target_to_source.get(row[0])
            row[1] = None if source_key is None else source_values.get(source_key)
            cursor.updateRow(row)

    return target_dataset


def get_spatial_reference(dataset):
    try:
        return arcpy.Describe(dataset).spatialReference
    except Exception:
        return None


def write_bed_assessment_points(output_path, rows, input_info, extra_fields, spatial_reference=None):
    output_folder = os.path.dirname(output_path)
    output_name = os.path.basename(output_path)
    if output_folder == "":
        output_folder = arcpy.env.workspace

    create_result = arcpy.management.CreateFeatureclass(
        output_folder,
        output_name,
        "POINT",
        spatial_reference=spatial_reference,
    )
    output_feature_class = create_result.getOutput(0)

    output_field_names = []
    used_field_names = set()

    for field_name in input_info["field_names"]:
        if field_name in used_field_names:
            continue
        field_definition = input_info["field_definitions"].get(field_name)
        if field_definition is None:
            continue
        if not _add_arcgis_field(output_feature_class, field_definition):
            continue
        output_field_names.append(field_name)
        used_field_names.add(field_name)

    for field_info in extra_fields:
        field_name = field_info["name"]
        if field_name in used_field_names:
            continue
        _add_simple_arcgis_field(output_feature_class, field_info)
        output_field_names.append(field_name)
        used_field_names.add(field_name)

    with arcpy.da.InsertCursor(output_feature_class, ["SHAPE@XY"] + output_field_names) as cursor:
        for row in rows:
            x_value = row.get("X")
            y_value = row.get("Y")
            geometry = None
            if x_value is not None and y_value is not None:
                geometry = (x_value, y_value)
            cursor.insertRow([geometry] + [row.get(field_name) for field_name in output_field_names])

    return output_feature_class


def _add_simple_arcgis_field(output_feature_class, field_info):
    dtype = field_info["dtype"]
    if dtype == "str":
        arcpy.management.AddField(
            output_feature_class,
            field_info["name"],
            "TEXT",
            field_length=field_info.get("max_length"),
        )
    elif dtype == "int":
        arcpy.management.AddField(output_feature_class, field_info["name"], "LONG")
    else:
        arcpy.management.AddField(output_feature_class, field_info["name"], "DOUBLE")


def read_point_dataset_any(dataset, field_names=None):
    return read_point_dataset(dataset, field_names)


def write_output_table(output_path, rows, input_info, extra_fields):
    output_folder = os.path.dirname(output_path)
    output_name = os.path.basename(output_path)
    if output_folder == "":
        output_folder = arcpy.env.workspace

    create_result = arcpy.management.CreateTable(output_folder, output_name)
    output_table = create_result.getOutput(0)

    output_field_names = []
    used_field_names = set()

    for field_name in input_info["field_names"]:
        field_key = str(field_name).lower()
        if field_key in used_field_names:
            continue
        field_definition = input_info["field_definitions"].get(field_name)
        if field_definition is None:
            continue
        if not _add_arcgis_field_like(output_table, field_name, field_definition):
            continue
        output_field_names.append(field_name)
        used_field_names.add(field_key)

    for field_info in extra_fields:
        field_name = field_info["name"]
        field_key = str(field_name).lower()
        if field_key in used_field_names:
            continue
        field_definition = field_info.get("field_definition")
        if field_definition is not None:
            if not _add_arcgis_field_like(output_table, field_name, field_definition, field_info.get("dtype", "float")):
                continue
        else:
            _add_simple_arcgis_field(output_table, field_info)
        output_field_names.append(field_name)
        used_field_names.add(field_key)

    with arcpy.da.InsertCursor(output_table, output_field_names) as cursor:
        for row in rows:
            cursor.insertRow([row.get(field_name) for field_name in output_field_names])

    return output_table


def _add_arcgis_field_like(output_table, output_field_name, field_definition, fallback_dtype="float"):
    field_type = {
        "String": "TEXT",
        "SmallInteger": "SHORT",
        "Integer": "LONG",
        "BigInteger": "BIGINTEGER",
        "Single": "FLOAT",
        "Double": "DOUBLE",
        "Date": "DATE",
        "DateOnly": "DATEONLY",
        "TimeOnly": "TIMEONLY",
        "TimestampOffset": "TIMESTAMPOFFSET",
        "GUID": "GUID",
        "GlobalID": "GUID",
    }.get(field_definition.type)

    if field_type is None:
        _add_simple_arcgis_field(
            output_table,
            {"name": output_field_name, "dtype": fallback_dtype},
        )
        return True

    add_field_kwargs = {}
    if field_type == "TEXT" and field_definition.length not in [None, 0]:
        add_field_kwargs["field_length"] = field_definition.length
    if field_type in ["FLOAT", "DOUBLE"]:
        if field_definition.precision not in [None, 0]:
            add_field_kwargs["field_precision"] = field_definition.precision
        if field_definition.scale not in [None, 0]:
            add_field_kwargs["field_scale"] = field_definition.scale
    if field_definition.aliasName not in [None, ""]:
        add_field_kwargs["field_alias"] = field_definition.aliasName

    arcpy.management.AddField(output_table, output_field_name, field_type, **add_field_kwargs)
    return True


def open_vector_dataset(dataset, layer_name=None):
    del layer_name
    return dataset


def read_table_dataset_with_oid(dataset, field_names=None):
    available_fields = [field for field in arcpy.ListFields(dataset) if field.type not in ["Geometry", "OID"]]
    available_field_names = [field.name for field in available_fields]

    if field_names is None or len(field_names) == 0:
        selected_field_names = available_field_names
    else:
        selected_field_names = list(field_names)
        missing_fields = [field_name for field_name in selected_field_names if field_name not in available_field_names]
        if len(missing_fields) != 0:
            raise ValueError(f"Field(s) not found in '{dataset}': {missing_fields}")

    field_definitions = {}
    for field in available_fields:
        if field.name in selected_field_names:
            field_definitions[field.name] = field

    records = []
    cursor_fields = list(selected_field_names) + ["OID@"]
    for row in arcpy.da.SearchCursor(dataset, cursor_fields):
        record = {"_oid": row[len(selected_field_names)]}
        for index, field_name in enumerate(selected_field_names):
            record[field_name] = row[index]
        records.append(record)

    return {
        "records": records,
        "field_names": selected_field_names,
        "field_definitions": field_definitions,
    }


def read_feature_extents(dataset, field_names=None):
    available_fields = [field for field in arcpy.ListFields(dataset) if field.type not in ["Geometry", "OID"]]
    available_field_names = [field.name for field in available_fields]

    if field_names is None or len(field_names) == 0:
        selected_field_names = available_field_names
    else:
        selected_field_names = list(field_names)
        missing_fields = [field_name for field_name in selected_field_names if field_name not in available_field_names]
        if len(missing_fields) != 0:
            raise ValueError(f"Field(s) not found in '{dataset}': {missing_fields}")

    field_definitions = {}
    for field in available_fields:
        if field.name in selected_field_names:
            field_definitions[field.name] = field

    records = []
    cursor_fields = list(selected_field_names) + ["SHAPE@", "OID@"]
    for row in arcpy.da.SearchCursor(dataset, cursor_fields):
        shape = row[len(selected_field_names)]
        extent = None if shape is None else shape.extent
        record = {
            "_oid": row[len(selected_field_names) + 1],
            "XMin": None if extent is None else extent.XMin,
            "YMin": None if extent is None else extent.YMin,
            "XMax": None if extent is None else extent.XMax,
            "YMax": None if extent is None else extent.YMax,
        }
        for index, field_name in enumerate(selected_field_names):
            record[field_name] = row[index]
        records.append(record)

    return {
        "records": records,
        "field_names": selected_field_names,
        "field_definitions": field_definitions,
    }


class _PolygonLookup:
    def __init__(self, dataset):
        self.records = []
        for shape, oid_value in arcpy.da.SearchCursor(dataset, ["SHAPE@", "OID@"]):
            if shape is None:
                continue
            extent = shape.extent
            self.records.append({
                "_oid": oid_value,
                "geometry": shape,
                "XMin": float(extent.XMin),
                "YMin": float(extent.YMin),
                "XMax": float(extent.XMax),
                "YMax": float(extent.YMax),
            })

    def find_containing_feature(self, x_value, y_value):
        point = arcpy.Point(float(x_value), float(y_value))
        for record in self.records:
            if (
                record["XMin"] <= x_value <= record["XMax"]
                and record["YMin"] <= y_value <= record["YMax"]
                and record["geometry"].contains(point)
            ):
                return record
        return None


def build_polygon_lookup(dataset):
    return _PolygonLookup(dataset)


def write_tiling_polygons(output_folder, records, spatial_reference=None):
    output_path = os.path.join(output_folder, "polyzones.shp")
    if arcpy.Exists(output_path):
        arcpy.Delete_management(output_path)

    arcpy.CreateFeatureclass_management(
        output_folder,
        "polyzones.shp",
        "POLYGON",
        spatial_reference=spatial_reference,
    )
    arcpy.AddField_management(output_path, "GRID_CODE", "LONG")
    arcpy.AddField_management(output_path, "Lake_ID", "LONG")

    with arcpy.da.InsertCursor(output_path, ["GRID_CODE", "SHAPE@", "Lake_ID"]) as cursor:
        for record in records:
            array = arcpy.Array([
                arcpy.Point(record["XMin"], record["YMin"]),
                arcpy.Point(record["XMin"], record["YMax"]),
                arcpy.Point(record["XMax"], record["YMax"]),
                arcpy.Point(record["XMax"], record["YMin"]),
            ])
            polygon = arcpy.Polygon(array, spatial_reference)
            cursor.insertRow([record["GRID_CODE"], polygon, record["Lake_ID"]])

    return output_path


def write_tiling_source_points(output_folder, records, spatial_reference=None):
    output_path = os.path.join(output_folder, "sourcepoints.shp")
    if arcpy.Exists(output_path):
        arcpy.Delete_management(output_path)

    arcpy.CreateFeatureclass_management(
        output_folder,
        "sourcepoints.shp",
        "POINT",
        spatial_reference=spatial_reference,
    )
    arcpy.AddField_management(output_path, "ZoneID", "LONG")
    arcpy.AddField_management(output_path, "fpid", "LONG")

    with arcpy.da.InsertCursor(output_path, ["ZoneID", "fpid", "SHAPE@XY"]) as cursor:
        for record in records:
            cursor.insertRow([record["ZoneID"], record["fpid"], (record["X"], record["Y"])])

    return output_path


def write_hydraulic_envelopezones(output_folder, records, spatial_reference=None):
    output_path = os.path.join(output_folder, "envelopezones.shp")
    if arcpy.Exists(output_path):
        arcpy.Delete_management(output_path)

    arcpy.CreateFeatureclass_management(
        output_folder,
        "envelopezones.shp",
        "POLYGON",
        spatial_reference=spatial_reference,
    )
    arcpy.AddField_management(output_path, "GRID_CODE", "LONG")
    arcpy.AddField_management(output_path, "Lake_ID", "LONG")

    with arcpy.da.InsertCursor(output_path, ["GRID_CODE", "Lake_ID", "SHAPE@"]) as cursor:
        for record in records:
            array = arcpy.Array([
                arcpy.Point(record["XMin"], record["YMin"]),
                arcpy.Point(record["XMin"], record["YMax"]),
                arcpy.Point(record["XMax"], record["YMax"]),
                arcpy.Point(record["XMax"], record["YMin"]),
            ])
            polygon = arcpy.Polygon(array, spatial_reference)
            cursor.insertRow([record["GRID_CODE"], record["Lake_ID"], polygon])

    return output_path


def write_hydraulic_inbci(output_folder, records, spatial_reference=None):
    output_path = os.path.join(output_folder, "inbci.shp")
    if arcpy.Exists(output_path):
        arcpy.Delete_management(output_path)

    arcpy.CreateFeatureclass_management(
        output_folder,
        "inbci.shp",
        "POINT",
        spatial_reference=spatial_reference,
    )
    arcpy.AddField_management(output_path, "zoneid", "LONG")
    arcpy.AddField_management(output_path, "flowacc", "LONG")
    arcpy.AddField_management(output_path, "type", "TEXT", field_length=16)
    arcpy.AddField_management(output_path, "fpid", "LONG")

    with arcpy.da.InsertCursor(output_path, ["zoneid", "flowacc", "type", "fpid", "SHAPE@XY"]) as cursor:
        for record in records:
            cursor.insertRow([
                int(record["zoneid"]),
                int(round(float(record["flowacc"]))),
                record["type"],
                int(record["fpid"]),
                (float(record["X"]), float(record["Y"])),
            ])

    return output_path


def write_hydraulic_outbci(output_folder, records, spatial_reference=None):
    output_path = os.path.join(output_folder, "outbci.shp")
    if arcpy.Exists(output_path):
        arcpy.Delete_management(output_path)

    arcpy.CreateFeatureclass_management(
        output_folder,
        "outbci.shp",
        "POINT",
        spatial_reference=spatial_reference,
    )
    arcpy.AddField_management(output_path, "zoneid", "LONG")
    arcpy.AddField_management(output_path, "side", "TEXT", field_length=1)

    with arcpy.da.InsertCursor(output_path, ["zoneid", "side", "SHAPE@XY"]) as cursor:
        for record in records:
            cursor.insertRow([
                int(record["zoneid"]),
                record["side"],
                (float(record["X"]), float(record["Y"])),
            ])

    return output_path


def write_point_features(output_path, features, input_info=None, extra_fields=None, spatial_reference=None):
    from RiverNetworkTools import ensure_point_feature

    if input_info is None:
        input_info = {"field_names": [], "field_definitions": {}}
    if extra_fields is None:
        extra_fields = []

    output_folder = os.path.dirname(output_path)
    output_name = os.path.basename(output_path)
    if output_folder == "":
        output_folder = arcpy.env.workspace

    create_result = arcpy.management.CreateFeatureclass(
        output_folder,
        output_name,
        "POINT",
        spatial_reference=spatial_reference,
    )
    output_feature_class = create_result.getOutput(0)
    output_field_names = _prepare_output_feature_fields(output_feature_class, input_info, extra_fields)

    with arcpy.da.InsertCursor(output_feature_class, ["SHAPE@XY"] + output_field_names) as cursor:
        for raw_feature in features:
            feature = ensure_point_feature(raw_feature)
            cursor.insertRow(
                [(float(feature.point.x), float(feature.point.y))]
                + [feature.attributes.get(field_name) for field_name in output_field_names]
            )

    return output_feature_class


def write_line_features(output_path, features, input_info=None, extra_fields=None, spatial_reference=None, has_m=False):
    from RiverNetworkTools import ensure_line_feature

    if input_info is None:
        input_info = {"field_names": [], "field_definitions": {}}
    if extra_fields is None:
        extra_fields = []

    output_folder = os.path.dirname(output_path)
    output_name = os.path.basename(output_path)
    if output_folder == "":
        output_folder = arcpy.env.workspace

    create_result = arcpy.management.CreateFeatureclass(
        output_folder,
        output_name,
        "POLYLINE",
        spatial_reference=spatial_reference,
        has_m="ENABLED" if has_m else "DISABLED",
    )
    output_feature_class = create_result.getOutput(0)
    output_field_names = _prepare_output_feature_fields(output_feature_class, input_info, extra_fields)

    with arcpy.da.InsertCursor(output_feature_class, ["SHAPE@"] + output_field_names) as cursor:
        for raw_feature in features:
            feature = ensure_line_feature(raw_feature)
            vertices = arcpy.Array()
            for vertex in feature.vertices:
                point = arcpy.Point(float(vertex.x), float(vertex.y))
                if has_m and vertex.m is not None:
                    point.M = float(vertex.m)
                vertices.add(point)
            geometry = arcpy.Polyline(vertices, spatial_reference, False, bool(has_m))
            cursor.insertRow([geometry] + [feature.attributes.get(field_name) for field_name in output_field_names])

    return output_feature_class


def update_line_attributes(dataset, features, key_field, update_fields, extra_fields=None):
    from RiverNetworkTools import ensure_line_feature

    if extra_fields is None:
        extra_fields = []

    existing_field_names = {field.name.lower() for field in arcpy.ListFields(dataset)}
    for field_info in extra_fields:
        if field_info["name"].lower() in existing_field_names:
            continue
        _add_simple_arcgis_field(dataset, field_info)
        existing_field_names.add(field_info["name"].lower())

    values_by_key = {}
    for raw_feature in features:
        feature = ensure_line_feature(raw_feature)
        key_value = feature.attributes.get(key_field)
        if key_value is None:
            continue
        values_by_key[key_value] = [feature.attributes.get(field_name) for field_name in update_fields]

    with arcpy.da.UpdateCursor(dataset, [key_field] + list(update_fields)) as cursor:
        for row in cursor:
            key_value = row[0]
            if key_value not in values_by_key:
                continue
            new_values = values_by_key[key_value]
            for index, value in enumerate(new_values, start=1):
                row[index] = value
            cursor.updateRow(row)


def _prepare_output_feature_fields(output_feature_class, input_info, extra_fields):
    output_field_names = []
    used_field_names = set()

    for field_name in input_info["field_names"]:
        field_key = str(field_name).lower()
        if field_key in used_field_names:
            continue
        field_definition = input_info["field_definitions"].get(field_name)
        if field_definition is None:
            continue
        if not _add_arcgis_field_like(output_feature_class, field_name, field_definition):
            continue
        output_field_names.append(field_name)
        used_field_names.add(field_key)

    for field_info in extra_fields:
        field_name = field_info["name"]
        field_key = str(field_name).lower()
        if field_key in used_field_names:
            continue
        field_definition = field_info.get("field_definition")
        if field_definition is not None:
            if not _add_arcgis_field_like(
                output_feature_class,
                field_name,
                field_definition,
                field_info.get("dtype", "float"),
            ):
                continue
        else:
            _add_simple_arcgis_field(output_feature_class, field_info)
        output_field_names.append(field_name)
        used_field_names.add(field_key)

    return output_field_names
