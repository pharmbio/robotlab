#!/usr/bin/env python3
import logging
from flask import Flask
from LHC_runner import LHC_runner

# Constants
BIOTEK_PRODUCT = "MultiFloFX"
COM_PORT = "USB MultiFloFX sn:19041612"
PROTOCOLS_ROOT = "C:\\ProgramData\\BioTek\\Liquid Handling Control 2.22\\Protocols"
LHC_CALLER_CLI_PATH = "C:\\Program Files (x86)\\BioTek\\Liquid Handling Control 2.22\\LHC_CallerCLI.exe"
PORT = 6001

if __name__ == '__main__':
    # Init logging
    logging.basicConfig(level=logging.DEBUG)
    logging.info("Before start server")

    # Create runner object
    lhc_runner = LHC_runner(BIOTEK_PRODUCT,
                            COM_PORT,
                            PROTOCOLS_ROOT,
                            LHC_CALLER_CLI_PATH)

    # Create webserver and map rest-api to runner methods
    server = Flask(__name__)
    server.add_url_rule('/execute_protocol/<path:protocol_name>', 'execute_protocol', lhc_runner.execute_protocol)
    server.add_url_rule('/is_ready', 'is_ready', lhc_runner.is_ready)
    server.add_url_rule('/last_LHC_response', 'last_LHC_response', lhc_runner.get_last_LHC_response)
    server.run(port=PORT)

    #
    # Example rest-calls
    #
    # http://http://localhost:6001/execute_protocol/_FOR_anders/dispenser_prime_all_buffers.LHC
    # http://localhost:6001/last_LHC_response
    # http://localhost:6001/is_ready
    #
