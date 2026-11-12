import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "qgis_tools" / "modeling"))

from qgis.core import (
    QgsApplication, QgsCoordinateReferenceSystem, QgsGeometry, QgsPointXY,
    Qgis,
    QgsProcessingException, QgsVectorLayer,
)

from HydraulicSimPrep import compute_maxoutput_polygon, create_maxoutput

QgsApplication.setPrefixPath(os.environ.get("QGIS_PREFIX_PATH", ""), True)
_app = QgsApplication([], False)
_app.initQgis()

EXTENT = (0, 0, 100, 100)


def line(*pts):
    return QgsGeometry.fromPolylineXY([QgsPointXY(*p) for p in pts])


def pt(x, y):
    return QgsGeometry.fromPointXY(QgsPointXY(x, y))


class MaxOutputTest(unittest.TestCase):
    def test_closest_polygon_is_kept(self):
        river = [line((-10, 50), (110, 50)), line((50, -10), (50, 110))]
        poly = compute_maxoutput_polygon(EXTENT, QgsPointXY(100, 50), river)
        self.assertTrue(poly.contains(pt(95, 50)))
        self.assertFalse(poly.contains(pt(5, 50)))

    def test_single_point_gives_zone(self):
        poly = compute_maxoutput_polygon(EXTENT, QgsPointXY(0, 50), [line((-10, 50), (50, 50))])
        self.assertAlmostEqual(poly.area(), 10000)

    def test_buffer(self):
        river = [line((-10, 50), (110, 50)), line((50, -10), (50, 110))]
        base = compute_maxoutput_polygon(EXTENT, QgsPointXY(100, 50), river)
        buffered = compute_maxoutput_polygon(EXTENT, QgsPointXY(100, 50), river, 10)
        self.assertTrue(buffered.contains(pt(45, 50)))
        self.assertFalse(base.contains(pt(45, 50)))

    def test_no_intersection_raises(self):
        with self.assertRaises(QgsProcessingException):
            compute_maxoutput_polygon(EXTENT, QgsPointXY(0, 0), [line((20, 20), (30, 30))])

    @unittest.skipIf(Qgis.QGIS_VERSION_INT < 33800, "QgsField(QMetaType) needs QGIS >= 3.38")
    def test_create_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "maxoutput.gpkg")
            create_maxoutput(
                {1: EXTENT}, {1: QgsPointXY(0, 50)}, [line((-10, 50), (50, 50))],
                0, out, QgsCoordinateReferenceSystem("EPSG:32618"),
            )
            layer = QgsVectorLayer(f"{out}|layername=maxoutput", "m", "ogr")
            self.assertEqual([f["zoneid"] for f in layer.getFeatures()], [1])


if __name__ == "__main__":
    unittest.main()
