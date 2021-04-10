#!/usr/bin/env python3
import logging
import subprocess
import sys
import os.path
import threading
import traceback
import time
from flask import Flask, json
from flask import jsonify


class LHC_runner:

    def __init__(self, product_name, com_port, protocols_root, lhc_cli_path):
        # biotek product config
        self._product_name = product_name
        self._com_port = com_port
        self._protocols_root = protocols_root
        self._lhc_cli_path = lhc_cli_path
        
        # thread vars
        self._thread_lock = threading.Lock()
        self._thread_LHC = None
        self._last_LHC_response = None

    def resetAndActivate(self):
        logging.debug("Inside resetAndActivate")

        try:

            # Just clear response, nothing else to do
            self._clearLastLHCResponse()

            response = {"status": "OK",
                        "value": "",
                        "details": "LastLHCResponse cleared"}

        finally:
            logging.debug('Done finally')
            return jsonify(response)

    def execute_protocol(self, protocol_name):
        # Only allow one LHC thread running
        self._thread_lock.acquire()
        try:
            if self._is_LHC_ready():
                # Start a thread
                self._thread_LHC = threading.Thread(target=self._execute_protocol_threaded, args=([protocol_name]))
                self._thread_LHC.start()
                response = {"status": "OK",
                            "value": "",
                            "details": "Executed protocol in background thread"}
            else:
                # throw error:
                response = {"status": "WARNING",
                            "value": "",
                            "details": "LHC is busy - will not run command"}
                logging.warning(response)

        except Exception as e:
            logging.error(traceback.format_exc())
            logging.error(e)
            response = [{"status": "ERROR",
                        "value": "",
                        "details": "See log for traceback"}]
            
        finally:
            self._thread_lock.release()
            logging.debug('Done finally')
            return jsonify(response)
            
    def simulate_protocol(self, time):
        # Only allow one LHC thread running
        self._thread_lock.acquire()
        try:
            if self._is_LHC_ready():
                # Start a thread
                self._thread_LHC = threading.Thread(target=self._simulate_protocol_threaded, args=([time]))
                self._thread_LHC.start()
                response = {"status": "OK",
                            "value": "",
                            "details": "Executed protocol in background thread"}
            else:
                # throw error:
                response = {"status": "WARNING",
                            "value": "",
                            "details": "LHC is not ready - will not run command"}
                logging.warning(response)

        except Exception as e:
            logging.error(traceback.format_exc())
            logging.error(e)
            response = [{"status": "ERROR",
                        "value": "",
                        "details": "See log for traceback"}]
            
        finally:
            self._thread_lock.release()
            logging.debug('Done finally')
            return jsonify(response)


    def _execute_protocol_threaded(self, protocol_name):
        logging.info("Inside execute_protocol_threaded, protocol_name=" + protocol_name)

        try:
            protocol_path = os.path.join(self._protocols_root, protocol_name)        
            logging.info("protocol_path=" + protocol_path)

            #
            # Execute on server and set response
            #
            proc_out = subprocess.Popen([self._lhc_cli_path,
                                    self._product_name,
                                    self._com_port,
                                    "LHC_RunProtocol",
                                    protocol_path
                                    ],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT
                                    )
            stdout,stderr = proc_out.communicate()

            self._last_LHC_response = self._response2json(stdout.decode("utf-8"))

        except Exception as e:
            logging.error("Error in _execute_protocol_threaded")
            logging.error(traceback.format_exc())
            logging.error(e)
            
        finally:
            logging.info('last_LHC_response' + str(self._last_LHC_response))
            logging.info('Finished Thread')
    
    def _simulate_protocol_threaded(self, time):
        logging.info("Inside _simulate_protocol_threaded, time=" + time)

        try:
            
            time.sleep(time)

            self._last_LHC_response = {"status": "OK",
                                       "value": "",
                                       "details": "Simulation done, time=" + str(time)}

        except Exception as e:
            logging.error("Error in _simulate_protocol_threaded")
            logging.error(traceback.format_exc())
            logging.error(e)
            
        finally:
            logging.info('last_LHC_response' + str(self._last_LHC_response))
            logging.info('Finished Thread')

    def _response2json(self, input):
        logging.info("Inside _response2json=" + str(input))
        # Indata might contain linebreak that needs to get removed
        cleaned = input.replace('\r', '').replace('\n', '').replace('\\','\\\\')
        return json.loads(cleaned)

    def is_ready(self):
        logging.debug("Inside is_ready")

        if self._is_LHC_errored():
            response = {"status": "ERROR",
                        "value": False,
                        "details": self._last_LHC_response}
        else:
            is_ready = not self._is_LHC_busy()
            response = {"status": "OK",
                        "value": is_ready,
                        "details": ""}
        return jsonify(response)

    def get_last_LHC_response(self):
        logging.debug("Inside get_last_LHC_response")
        response = {"status": "OK",
                    "value": self._last_LHC_response,
                    "details": ""}
        return jsonify(response)

    def _clearLastLHCResponse(self):
        self._last_LHC_response = None

    def _is_LHC_ready(self):
        logging.debug("Inside _is_LHC_ready")

        if self._is_LHC_busy() or self._is_LHC_errored():
            return False
        else:
            return True

    def _is_LHC_busy(self):
        if self._thread_LHC is None or self._thread_LHC.is_alive() == False:
            return False
        else:
            return True

    def _is_LHC_errored(self):
        is_errored = False
        if self._last_LHC_response is not None:
            logging.debug("last-resp" + str(self._last_LHC_response))
            if self._last_LHC_response.get("status") == "99":
                is_errored = True
        return is_errored


if __name__ == '__main__':
    # Init logging
    logging.basicConfig(level=logging.DEBUG)
    logging.info("Before start server")

    # Constants
    BIOTEK_PRODUCT = "MultiFloFX"
    COM_PORT = "USB MultiFloFX sn:19041612"
    PROTOCOLS_ROOT = "C:\\ProgramData\\BioTek\\Liquid Handling Control 2.22\\Protocols"
    LHC_CALLER_CLI_PATH = "C:\\Program Files (x86)\\BioTek\\Liquid Handling Control 2.22\\LHC_CallerCLI.exe"
    PORT = 5050

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
    # http://http://localhost:5050/execute_protocol/test-protocols/dispenser_prime_all_buffers.LHC
    # http://localhost:5050/last_LHC_response
    # http://localhost:5050/is_ready
    #
