import os
from datetime import timedelta

from flask import Flask, jsonify, request, current_app
from dateutil.parser import parse
from flask_cors import CORS
from pytz import UTC
from werkzeug.exceptions import Unauthorized, InternalServerError

from analyzer import DataLoader, DataAnalyzer

app = Flask(__name__)
CORS(app)

app.config['TRACCAR_URL'] = os.getenv("TRACCAR_URL")


def map_events_to_dicts(events, with_geopoints=True):
    return [event.to_dict(with_geopoints) for event in events]


@app.route('/api/device/<device>/events/<day>')
def get_events(device, day):
    if request.authorization is None:
        return jsonify({}), 401

    try:
        device_id = int(device)
    except ValueError:
        return jsonify({'error': 'Invalid device argument'})

    try:
        date = parse(day)
    except ValueError:
        return jsonify({'error': 'Invalid date argument'}), 400

    date = date.replace(microsecond=0, second=0)
    date = date.astimezone(UTC)

    dl = DataLoader(
        current_app.config['TRACCAR_URL'],
        request.authorization['username'],
        request.authorization['password']
    )

    try:
        geofences = dl.get_geofences()
        positions = dl.get_positions(device_id, date_from=date, date_to=date + timedelta(days=1))
    except Unauthorized:
        return jsonify({'error': 'Unauthorized'}), 401
    except InternalServerError:
        return jsonify({'error': 'Internal server error'}), 500

    da = DataAnalyzer(geofences)
    events = da.map_positions_to_events(positions)

    with_geopoints = request.args.get('geopoints', 'true') == 'true'
    return jsonify(date=date.isoformat(), events=map_events_to_dicts(events, with_geopoints))


if __name__ == '__main__':
    app.run(host='0.0.0.0')
