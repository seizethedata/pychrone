import osmnx as ox, numpy as np, networkx as nx
from shapely.ops import cascaded_union, polygonize
from scipy.spatial import Delaunay
import math
import shapely.geometry as geometry
import geojson as gj
import geopy.distance


def Create_isochrone(lon, lat, time, speed=4.5, output='geojson', route='walk'):

    '''
    Main module function. Takes:
        lat, lon of point to build isochrone from,
        time of travel to limit isochrone,
        speed of travel (default is 4.5),
        output format - geojson or shape,
        route type - walk, drive, bike;
    Returns isochrone polygon in geojson or shape.
    '''

    def GenerateIsoPoints(lon, lat, time, speed):

        '''
        Function generates points cloud of isochrone from OSM
        depending on route type.
        Returns list of points.
        '''

        distance = speed * 1000 / 60 * time * 1.5

        streets_graph = ox.graph_from_point([lat, lon], dist=distance, network_type=route, simplify=False)

        center_node = ox.get_nearest_node(streets_graph, (lat, lon), method='euclidean')

        streets_graph.add_node('dummy', osmid=999999999, x=lon, y=lat)
        dummy_length = geopy.distance.geodesic((streets_graph.nodes['dummy']['y'], streets_graph.nodes['dummy']['x']),
                                               (streets_graph.nodes[center_node]['y'], streets_graph.nodes[center_node]['x'])).m
        streets_graph.add_edge('dummy', center_node, length=dummy_length)

        projected_graph = ox.project_graph(streets_graph)

        travel_speed = speed

        meters_per_minute = travel_speed * 1000 / 60
        for u, v, k, data in projected_graph.edges(data=True, keys=True):
            data['time'] = data['length'] / meters_per_minute

        subgraph = nx.ego_graph(projected_graph, center_node, radius=time, distance='time')
        node_points = [[data['lon'], data['lat']] for node, data in subgraph.nodes(data=True)]
        points = np.array(node_points)
        return points

    def alpha_shape(points, alpha):

        '''
        Function optimizes ishorhone with alpha-shape algorythm and returns polgon
        '''

        if len(points) < 4:
            return geometry.MultiPoint(list(points)).convex_hull

        def add_edge(edges, edge_points, coords, i, j):

            if (i, j) in edges or (j, i) in edges:
                return
            edges.add((i, j))
            edge_points.append(coords[[i, j]])

        coords = np.array([point for point in points])
        tri = Delaunay(coords)
        edges = set()
        edge_points = []

        for ia, ib, ic in tri.vertices:
            pa = coords[ia]
            pb = coords[ib]
            pc = coords[ic]
            a = math.sqrt((pa[0] - pb[0]) ** 2 + (pa[1] - pb[1]) ** 2)
            b = math.sqrt((pb[0] - pc[0]) ** 2 + (pb[1] - pc[1]) ** 2)
            c = math.sqrt((pc[0] - pa[0]) ** 2 + (pc[1] - pa[1]) ** 2)
            s = (a + b + c) / 2.0
            try:
                area = math.sqrt(s * (s - a) * (s - b) * (s - c))
            except ValueError:
                area = 0.0001
            if area == 0:
                area = 0.0001

            circum_r = a * b * c / (4.0 * area)
            if circum_r < 1.0 / alpha:
                add_edge(edges, edge_points, coords, ia, ib)
                add_edge(edges, edge_points, coords, ib, ic)
                add_edge(edges, edge_points, coords, ic, ia)
        m = geometry.MultiLineString(edge_points)
        triangles = list(polygonize(m))
        return cascaded_union(triangles), edge_points

    iso_points = GenerateIsoPoints(lon, lat, time, speed)
    isochrone = None
    for alpha in range(751, -1, -50):
        try:
            concave_hull, edge_points = alpha_shape(iso_points, alpha=alpha)

            if concave_hull.geom_type == 'MultiPolygon':
                continue

            else:
                if output == 'geojson':
                    isochrone = geometry.polygon.orient(concave_hull, sign=1)
                    return gj.loads(gj.dumps(isochrone))
                elif output == 'shape':
                    return isochrone
        except:
            continue
