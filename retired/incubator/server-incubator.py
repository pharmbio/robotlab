#!/usr/bin/env python3
import logging
import sys
from flask import Flask

# Import client code
sys.path.append('/pharmbio/incubator-automation')
from Incubator import Incubator

# Constants
PORT = 5001

if __name__ == '__main__':
    # Init logging
    logging.basicConfig(level=logging.DEBUG)
    logging.info("Before start server")

    # Create Incubator object
    incubator = Incubator()

    # Create webserver and map rest-api to Incubator methods
    server = Flask(__name__)
    server.add_url_rule('/open', 'open', incubator.open)
    server.add_url_rule('/is_open', 'is_open', incubator.is_open)
    server.add_url_rule('/close', 'close', incubator.close)
    server.add_url_rule('/is_closed', 'is_closed', incubator.is_closed)
    server.add_url_rule('/is_ready', 'is_ready', incubator.is_ready)

    server.run(host='0.0.0.0', port=PORT)

    #
    # Example rest-calls
    #
    # http://localhost:5001/open
    # http://localhost:5001/close
    # http://localhost:5001/is_open
    #
