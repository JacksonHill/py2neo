import pytest

from py2neo import Node, Relationship

from . import TestBase
from py2neo.ext.spatial.exceptions import (
    GeometryExistsError, GeometryNotFoundError, InvalidWKTError,
    NodeNotFoundError)
from py2neo.ext.spatial.plugin import NAME_PROPERTY, WKT_PROPERTY
from py2neo.ext.spatial.util import parse_lat_long_to_point


class TestGeometries(TestBase):
    def test_poi_on_wkt_encoded_layer(self, spatial):
        spatial.create_layer("uk")
        bristol = (51.454513, -2.58791)
        lat, lon = bristol

        node = spatial.create_point_of_interest(
            poi_name="bristol", layer_name="uk", latitude=lat, longitude=lon)

        node_id = int(node.uri.path.segments[-1])
        query = (
            "MATCH (n)<-[:RTREE_REFERENCE]-(bbox)<-[:RTREE_ROOT]-(layer) "
            "WHERE id(n) = {node_id} "
            "RETURN layer"
        )
        params = {
            'node_id': node_id,
        }

        results = spatial.graph.cypher.execute(query, params)
        result = results[0]
        layer_node = result.layer

        assert layer_node.properties['geomencoder'].endswith('WKTGeometryEncoder')

    def test_geometry_on_wkt_encoded_layer(self, spatial, cornwall_wkt):
        geometry_name = "shape"
        spatial.create_layer("cornwall")
        node = spatial.create_geometry(
            geometry_name=geometry_name,
            wkt_string=cornwall_wkt,
            layer_name="cornwall"
        )

        node_id = int(node.uri.path.segments[-1])
        query = (
            "MATCH (n)<-[:RTREE_REFERENCE]-(bbox)<-[:RTREE_ROOT]-(layer) "
            "WHERE id(n) = {node_id} "
            "RETURN layer"
        )
        params = {
            'node_id': node_id,
        }

        results = spatial.graph.cypher.execute(query, params)
        result = results[0]
        layer_node = result.layer

        assert layer_node.properties['geomencoder'].endswith('WKTGeometryEncoder')

    def test_create_polygon(self, spatial, cornwall_wkt):
        graph = spatial.graph
        geometry_name = "shape"
        spatial.create_layer("cornwall")
        spatial.create_geometry(
            geometry_name=geometry_name,
            wkt_string=cornwall_wkt,
            layer_name="cornwall"
        )

        assert self._geometry_exists(graph, geometry_name)

    def test_create_point_of_interest(self, spatial):
        spatial.create_layer(layer_name="uk")

        # stonehenge
        lat = 51.178882
        lon = -1.826215

        poi_node = spatial.create_point_of_interest(
            poi_name="stonehenge", layer_name="uk", latitude=lat, longitude=lon)
        
        assert poi_node.properties['geometry_name'] == "stonehenge"

    def test_update_point_of_interest(self, spatial):
        spatial.create_layer(layer_name="uk")

        # not stonehenge!
        lat = 31.5
        lon = -100.1
        bad_geometry = 'POINT ({} {})'.format(lon, lat)

        spatial.create_point_of_interest(
            poi_name="stonehenge", layer_name="uk", latitude=lat, longitude=lon)

        node = self.get_geometry_node(spatial.graph, "stonehenge")

        assert node.properties['wkt'] == bad_geometry

        # stonehenge
        lat = 51.178882
        lon = -1.826215
        new_geometry = 'POINT ({} {})'.format(lon, lat)

        spatial.update_geometry(geometry_name="stonehenge", wkt_string=new_geometry)
        node.pull()

        assert node.properties['wkt'] == new_geometry

    def test_create_point_geometries(self, spatial):
        graph = spatial.graph
        layer_name = 'point_layer'
        spatial.create_layer(layer_name)

        points = [
            ('a', (5.5, -4.5)), ('b', (2.5, -12.5)), ('c', (30.5, 10.5))
        ]

        for geometry_name, coords in points:
            shape = parse_lat_long_to_point(*coords)
            assert shape.type == 'Point'

            spatial.create_geometry(
                geometry_name=geometry_name, wkt_string=shape.wkt,
                layer_name=layer_name)

            geometry_node = self.get_geometry_node(spatial, geometry_name)
            assert geometry_node

            # ensure it has been given a label
            labels = geometry_node.get_labels()

            assert 'Point' in labels
            assert layer_name in labels

    def test_make_existing_node_spatially_aware(self, spatial):
        graph = spatial.graph
        node = Node(address="300 St John Street, London.")
        graph.create(node)
        node_id = int(node.uri.path.segments[-1])
        coords = (51.528453, -0.104489)
        shape = parse_lat_long_to_point(*coords)

        spatial.create_layer("mylayer")
        updated_node_repr = spatial.add_node_to_layer_by_id(
            node_id=node_id, geometry_name="mygeom", wkt_string=shape.wkt,
            layer_name="mylayer")

        node = next(graph.find(
            label="mylayer", property_key=NAME_PROPERTY,
            property_value="mygeom"))

        labels = node.get_labels()
        properties = node.get_properties()

        assert labels == set(['py2neo_spatial', 'mylayer', 'Point'])
        assert properties[NAME_PROPERTY] == "mygeom"
        assert properties['address'] == "300 St John Street, London."

    def test_add_node_to_layer_return_values(self, spatial):
        graph = spatial.graph
        node = Node(address="300 St John Street, London.")
        graph.create(node)
        node_id = int(node.uri.path.segments[-1])
        coords = (51.528453, -0.104489)
        shape = parse_lat_long_to_point(*coords)

        spatial.create_layer("mylayer")
        node = spatial.add_node_to_layer_by_id(
            node_id=node_id, geometry_name="mygeom", wkt_string=shape.wkt,
            layer_name="mylayer")

        assert isinstance(node, Node)
        assert str(node_id) in str(node.uri)

    def test_geometry_uniqueness(self, spatial, cornwall_wkt):
        geometry_name = "shape"

        spatial.create_layer("my_layer")
        spatial.create_geometry(
            geometry_name=geometry_name, wkt_string=cornwall_wkt,
            layer_name="my_layer")

        with pytest.raises(GeometryExistsError):
            spatial.create_geometry(
                geometry_name=geometry_name, wkt_string=cornwall_wkt,
                layer_name="my_layer")

    def test_create_geometry(self, spatial, uk, cornwall_wkt):
        spatial.create_geometry(
            geometry_name="cornwall", wkt_string=cornwall_wkt,
            layer_name="uk")

        assert self._geometry_exists(spatial.graph, "cornwall")

    def test_delete_geometry(self, spatial, uk, cornwall, cornwall_wkt):
        graph = spatial.graph
        assert self._geometry_exists(graph, "cornwall")
        spatial.delete_geometry("cornwall", cornwall_wkt, "uk")
        assert not self._geometry_exists(graph, "cornwall")

    def test_update_geometry(self, spatial):
        graph = spatial.graph

        # bad data
        bad_eiffel_tower = (57.322857, -4.424382)
        bad_shape = parse_lat_long_to_point(*bad_eiffel_tower)

        spatial.create_layer("paris")
        spatial.create_geometry(
            geometry_name="eiffel_tower", wkt_string=bad_shape.wkt,
            layer_name="paris")

        assert self._geometry_exists(graph, "eiffel_tower")

        # good data
        eiffel_tower = (48.858370, 2.294481)
        shape = parse_lat_long_to_point(*eiffel_tower)

        spatial.update_geometry(
            geometry_name="eiffel_tower", wkt_string=shape.wkt)

        node = self.get_geometry_node(graph, "eiffel_tower")
        node_properties = node.get_properties()

        assert node_properties['wkt'] == shape.wkt

    def test_update_geometry_return_value(self):
        pass

    def test_update_geometry_with_invalid_wkt(self, spatial, uk, cornwall):
        invalid_wkt = 'Shape(1, 234)'

        with pytest.raises(InvalidWKTError):
            spatial.update_geometry(
                geometry_name="cornwall", wkt_string=invalid_wkt)

    def test_update_geometry_not_found(self, spatial):
        coords = (57.322857, -4.424382)
        shape = parse_lat_long_to_point(*coords)

        with pytest.raises(GeometryNotFoundError):
            spatial.update_geometry("somewhere", shape.wkt)

    def test_get_geometries_in_bounding_box(self, spatial, uk, cornwall, devon):
        # very roughly, the uk
        minx, miny, maxx, maxy = -10, 40, 10, 80
        geometries = spatial.find_within_bounding_box(
            "uk", minx, miny, maxx, maxy)

        assert len(geometries) == 2
        
        expexted_geometry_names = {'cornwall', 'devon'}
        geometry_names = {
            geometry.properties['geometry_name'] for geometry in geometries}

        assert geometry_names == expexted_geometry_names

    def test_create_polygon(self, spatial):
        wkt_string = 'POLYGON ((30 10, 40 40, 20 40, 10 20, 30 10))'
        spatial.create_layer(layer_name="geometries")
        geometry = spatial.create_geometry(
            layer_name="geometries", geometry_name="polygon",
            wkt_string=wkt_string
        )

        assert isinstance(geometry, Node)
        assert 'Polygon' in geometry.labels

    def test_create_multipolygon(self, spatial):
        wkt_string = (
            'MULTIPOLYGON (((40 40, 20 45, 45 30, 40 40)), '
            '((20 35, 10 30, 10 10, 30 5, 45 20, 20 35), '
            '(30 20, 20 15, 20 25, 30 20)))'
        )
        spatial.create_layer(layer_name="geometries")
        geometry = spatial.create_geometry(
            layer_name="geometries", geometry_name="polygon",
            wkt_string=wkt_string
        )

        assert isinstance(geometry, Node)
        assert 'MultiPolygon' in geometry.labels
