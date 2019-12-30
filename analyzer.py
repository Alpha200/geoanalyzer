import requests


class Geofence:
    def __init__(self, name):
        self.name = name


class PolygonGeofence(Geofence):
    def __init__(self, name, area):
        super().__init__(name)
        self.area = area

    def __repr__(self) -> str:
        return "<PolygonGeofence {} {}>".format(self.name, self.area)


class CircleGeofence(Geofence):
    def __init__(self, name, middle, radius):
        super().__init__(name)
        self.middle = middle
        self.radius = radius

    def __repr__(self) -> str:
        return "<CircleGeofence {} ({}, {})>".format(self.name, self.middle, self.radius)


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
                middle = tuple(float(value) for value in middle_str.split(" "))
                return CircleGeofence(name, middle, radius)
            elif area_string.startswith("POLYGON"):
                info = area_string[9:-2]
                area = [tuple(float(value) for value in poly.split(" ")) for poly in info.split(", ")]
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
