import requests
from collections import deque
from dateutil.parser import parse
from geopy import distance
from geopy.geocoders import Nominatim
from abc import ABC, abstractmethod
from shapely.geometry import Point, Polygon, MultiPoint
from werkzeug.exceptions import Unauthorized, InternalServerError

geolocator = Nominatim(user_agent="geoanalyzer")


class Geofence(ABC):
    def __init__(self, name):
        self.name = name

    @abstractmethod
    def is_inside(self, point):
        return False


class PolygonGeofence(Geofence):
    def __init__(self, name, area):
        super().__init__(name)
        self.area = area

    def __repr__(self) -> str:
        return "<PolygonGeofence {} {}>".format(self.name, self.area)

    def is_inside(self, point):
        return self.area.contains(Point(point))

    def to_dict(self):
        return {
            'type': 'polygon',
            'name': self.name,
            'points': list(self.area.exterior.coords)
        }


class CircleGeofence(Geofence):
    def __init__(self, name, middle, radius):
        super().__init__(name)
        self.middle = middle
        self.radius = radius

    def __repr__(self) -> str:
        return "<CircleGeofence {} ({}, {})>".format(self.name, self.middle, self.radius)

    def is_inside(self, point):
        return distance.distance((self.middle.x, self.middle.y), point).m < self.radius

    def to_dict(self):
        return {
            'type': "circle",
            'name': self.name,
            'center': [self.middle.x, self.middle.y],
            'radius': self.radius
        }


class Event(ABC):
    def __init__(self):
        self.geopoints = []

    @property
    def d_from(self):
        return self.geopoints[0].date

    @property
    def d_to(self):
        return self.geopoints[-1].date


class ClusterEvent(Event):
    def __init__(self, geopoints):
        super().__init__()
        self.geopoints = geopoints

    @property
    def centroid(self):
        if len(self.geopoints) == 0:
            return None

        point = MultiPoint([point.position for point in self.geopoints]).centroid
        return point.x, point.y

    def to_dict(self, with_geopoints=True):
        location = geolocator.reverse("{}, {}".format(*self.centroid))

        result = {
            'event_type': "cluster",
            'from': self.d_from.isoformat(),
            'to': self.d_to.isoformat(),
            'centroid': self.centroid,
            'location': location.address
        }

        if with_geopoints:
            result["geopoints"] = [geopoint.to_dict() for geopoint in self.geopoints]

        return result

    def __repr__(self) -> str:
        return "<ClusterEvent {} - {}>".format(self.d_from, self.d_to)


class GeofenceEvent(Event):
    def __init__(self, geofence):
        super().__init__()
        self.geofence = geofence

    def to_dict(self, with_geopoints=True):
        result = {
            'event_type': "geofence",
            'from': self.d_from.isoformat(),
            'to': self.d_to.isoformat(),
            'geofence': self.geofence.to_dict(),
        }

        if with_geopoints:
            result["geopoints"] = [geopoint.to_dict() for geopoint in self.geopoints]

        return result

    def __repr__(self) -> str:
        return "<GeofenceEvent {} {} - {}>".format(self.geofence.name, self.d_from, self.d_to)


class TravelEvent(Event):
    def __init__(self):
        super().__init__()

    @property
    def distance(self):
        dist = 0

        for a, b in zip(self.geopoints, self.geopoints[1:]):
            dist += a.distance(b)

        return dist

    def to_dict(self, with_geopoints=True):
        result = {
            'event_type': "travel",
            'from': self.d_from.isoformat(),
            'to': self.d_to.isoformat(),
            'distance': self.distance,
        }

        if with_geopoints:
            result["geopoints"] = [geopoint.to_dict() for geopoint in self.geopoints]

        return result

    def __repr__(self) -> str:
        return "<TravelEvent {} {} - {}>".format(self.distance, self.d_from, self.d_to)


class GeoPosition:
    def __init__(self, date, position, accuracy):
        self.date = date
        self.position = position
        self.accuracy = accuracy

    def distance(self, other_position):
        """Returns the distance to other_position in m"""
        return distance.distance(
            self.position,
            other_position.position
        ).m

    def to_dict(self):
        return {
            'date': self.date.isoformat(),
            'latitude': self.position[0],
            'longitude': self.position[1],
            'accuracy': self.accuracy
        }


class DataLoader:
    def __init__(self, base_uri, username, password):
        self.base_uri = base_uri
        self.username = username
        self.password = password

    def get_geofences(self):
        def create_geofence(name, area_string):
            if area_string.startswith("CIRCLE"):
                info = area_string[8:-1]
                middle_str, radius = info.split(", ")
                radius = float(radius)
                middle = Point(tuple(float(value) for value in middle_str.split(" ")))
                return CircleGeofence(name, middle, radius)
            elif area_string.startswith("POLYGON"):
                info = area_string[9:-2]
                area = Polygon(shell=(tuple(float(value) for value in poly.split(" ")) for poly in info.split(", ")))
                return PolygonGeofence(name, area)
            else:
                return None

        r = requests.get("{}/api/geofences".format(self.base_uri), auth=(self.username, self.password))

        if r.status_code == 401:
            raise Unauthorized()
        elif r.status_code != 200:
            raise InternalServerError()

        data = r.json()

        geofences = [create_geofence(fence["name"], fence["area"]) for fence in data]
        return geofences

    def get_positions(self, device_id, date_from, date_to):
        r = requests.get("{base_uri}/api/positions?deviceId={device_id}&from={d_from}&to={d_to}".format(
            base_uri=self.base_uri,
            device_id=device_id,
            d_from=date_from.strftime("%Y-%m-%dT%H:%MZ"),
            d_to=date_to.strftime("%Y-%m-%dT%H:%MZ")
        ), auth=(self.username, self.password))

        r.raise_for_status()
        data = r.json()

        return [
            GeoPosition(
                parse(position["fixTime"]),
                (position['latitude'], position['longitude']),
                position['accuracy']
            ) for position in data
        ]


def is_cluster_valid(geopoints):
    points = MultiPoint([point.position for point in geopoints])
    return not any(distance.distance((points.centroid.x, points.centroid.y), (point.x, point.y)).m > 50 for point in points)


class DataAnalyzer:
    def __init__(self, geofences):
        self.geofences = geofences

    def get_geofence(self, position):
        for geofence in self.geofences:
            if geofence.is_inside(position):
                return geofence

        return None

    def map_positions_to_events(self, positions):
        events = []
        current_event = None
        last_geopoints = deque([], maxlen=3)

        for position in positions:
            current_geofence = self.get_geofence(position.position)

            if current_geofence is not None:
                if current_event is None:
                    current_event = GeofenceEvent(current_geofence)

                if isinstance(current_event, GeofenceEvent):
                    if current_event.geofence != current_geofence:
                        events.append(current_event)
                        current_event = GeofenceEvent(current_geofence)

                    current_event.geopoints.append(position)
                elif isinstance(current_event, TravelEvent):
                    events.append(current_event)
                    current_event = GeofenceEvent(current_geofence)
                    current_event.geopoints.append(position)
            else:
                if isinstance(current_event, GeofenceEvent):
                    events.append(current_event)
                    current_event = None
                elif isinstance(current_event, TravelEvent):
                    distance_between_points = position.distance(current_event.geopoints[-1])

                    if distance_between_points > 100:
                        current_event.geopoints.append(position)
                    else:
                        events.append(current_event)
                        current_event = None
                elif isinstance(current_event, ClusterEvent):
                    if is_cluster_valid(current_event.geopoints + [position]):
                        current_event.geopoints.append(position)
                    else:
                        events.append(current_event)
                        current_event = None
                    #elif is_cluster_valid(current_event.geopoints[1:] + [position]):
                        # TODO: Check if this cluster is better than the other
                else:
                    if len(last_geopoints) > 0:
                        distance_between_points = position.distance(last_geopoints[-1])

                        if distance_between_points > 100:
                            current_event = TravelEvent()
                            current_event.geopoints.append(last_geopoints[-1])
                            current_event.geopoints.append(position)
                        elif len(last_geopoints) >= 3:
                            possible_cluster = list(last_geopoints) + [position]
                            if is_cluster_valid(possible_cluster):
                                current_event = ClusterEvent(possible_cluster)

            last_geopoints.append(position)

        if current_event is not None:
            events.append(current_event)

        return events
