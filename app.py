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


def map_events_to_json(events, with_geopoints=True):
    return jsonify([event.to_dict(with_geopoints) for event in events])


@app.route('/api/device/<device>/events/<day>')
def get_events(device, day):
    if request.authorization is None:
        return jsonify({}), 401

    device_id = int(device)

    date = parse(day)
    date = date.replace(microsecond=0, second=0)
    date = date.astimezone(UTC)

    dl = DataLoader(traccar_conf["base_uri"], request.authorization['username'], request.authorization['password'])
    geofences = dl.get_geofences()
    positions = dl.get_positions(device_id, date_from=date, date_to=date + timedelta(days=1))

    da = DataAnalyzer(geofences)
    events = da.map_positions_to_events(positions)

    with_geopoints = request.args.get('geopoints', 'true') == 'true'
    return map_events_to_json(events, with_geopoints)


if __name__ == '__main__':
    app.run(host='0.0.0.0')
