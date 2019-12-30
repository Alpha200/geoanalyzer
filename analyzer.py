import requests
from dateutil.parser import parse
from geopy import distance
from abc import ABC, abstractmethod
from shapely.geometry import Point, Polygon


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


class CircleGeofence(Geofence):
    def __init__(self, name, middle, radius):
        super().__init__(name)
        self.middle = middle
        self.radius = radius

    def __repr__(self) -> str:
        return "<CircleGeofence {} ({}, {})>".format(self.name, self.middle, self.radius)

    def is_inside(self, point):
        return distance.distance((self.middle.x, self.middle.y), point).m < self.radius


class Event(ABC):
    def __init__(self, d_from, d_to):
        self.d_from = d_from
        self.d_to = d_to


class GeofenceEvent(Event):
    def __init__(self, d_from, d_to, geofence):
        super().__init__(d_from, d_to)
        self.geofence = geofence


class TravelEvent(Event):
    def __init__(self, d_from, d_to, distance):
        super().__init__(d_from, d_to)
        self.distance = distance


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
        r.raise_for_status()

        data = r.json()

        geofences = [create_geofence(fence["name"], fence["area"]) for fence in data]
        return geofences

    def get_positions(self, device_id, date_from, date_to):
        r = requests.get("{base_uri}/api/positions?deviceId={device_id}&from={d_from}Z&to={d_to}Z".format(
            base_uri=self.base_uri,
            device_id=device_id,
            d_from=date_from.isoformat(),
            d_to=date_to.isoformat()
        ), auth=(self.username, self.password))

        r.raise_for_status()
        return r.json()


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
        last_tp = None

        for index, position in enumerate(positions):
            current_geofence = self.get_geofence((position['latitude'], position['longitude']))
            current_tp = parse(position['fixTime'])

            if current_geofence is not None:
                if current_event is None:
                    current_event = GeofenceEvent(current_tp, None, current_geofence)
            else:
                if isinstance(current_event, GeofenceEvent):
                    current_event.d_to = last_tp
                    events.append(current_event)
                    current_event = None

            last_tp = current_tp

        if current_event is not None:
            current_event.d_to = last_tp
            events.append(current_event)

        return events
