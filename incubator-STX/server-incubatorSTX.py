#!/usr/bin/env python3
import logging
from flask import Flask
from IncubatorSTX import IncubatorSTX

# Constants
PORT = 5003

if __name__ == '__main__':
    # Init logging
    logging.basicConfig(level=logging.DEBUG)
    logging.info("Before start server")

    # Create Incubator object
    incubator = IncubatorSTX("STX", "130.238.44.60", 3333)

    # Create webserver and map rest-api to runner methods
    server = Flask(__name__)
    server.add_url_rule('/input_plate/<int:nPos>', 'inputPlate', incubator.inputPlate)
    server.add_url_rule('/output_plate/<int:nPos>', 'outputPlate', incubator.outputPlate)
    server.add_url_rule('/is_ready', 'is_ready', incubator.is_ready)
    server.add_url_rule('/resetAndActivate', 'resetAndActivate', incubator.resetAndActivate)
    server.add_url_rule('/last_STX_response', 'last_STX_response', incubator.get_last_STX_response)
    server.add_url_rule('/getClimate', 'getClimate', incubator.getClimate)
    server.add_url_rule('/getPresetClimate', 'getPresetClimate', incubator.getPresetClimate)
    server.add_url_rule('/setPresetClimate/<int:temp>/<int:humid>/<int:co2>/<int:n2>', 'setPresetClimate', incubator.setPresetClimate)
    server.run(host='0.0.0.0', port=PORT)

    #
    # Example rest-calls
    #
    # http://localhost:5003/is_ready
    # http://localhost:5003/resetAndActivate
    # 
    #
