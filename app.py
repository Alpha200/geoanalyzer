from datetime import timedelta

import yaml
from flask import Flask, jsonify, request
from dateutil.parser import parse
from flask_cors import CORS
from pytz import UTC

from analyzer import DataLoader, DataAnalyzer

app = Flask(__name__)
CORS(app)

with open("config.yaml", "r") as f:
    conf = yaml.safe_load(f)

traccar_conf = conf["traccar"]

dl = DataLoader(traccar_conf["base_uri"], traccar_conf["username"], traccar_conf["password"])


def map_events_to_json(events, with_geopoints=True):
    return jsonify([event.to_dict(with_geopoints) for event in events])


@app.route('/events/<day>')
def get_events(day):
    date = parse(day)
    date = date.replace(microsecond=0, second=0)
    date = date.astimezone(UTC)

    geofences = dl.get_geofences()
    positions = dl.get_positions(traccar_conf["device_id"], date_from=date, date_to=date + timedelta(days=1))

    da = DataAnalyzer(geofences)
    events = da.map_positions_to_events(positions)

    with_geopoints = request.args.get('geopoints', 'true') == 'true'
    return map_events_to_json(events, with_geopoints)


if __name__ == '__main__':
    app.run()
