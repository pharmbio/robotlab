#!/usr/bin/env python3
import logging
import subprocess
import sys
import os.path
import threading
import traceback
from flask import Flask, json


class LHC_runner:

    def __init__(self, product_name, com_port, protocols_root, lhc_cli_path):
        # biotek product config
        self.product_name = product_name
        self.com_port = com_port
        self.protocols_root = protocols_root
        self.lhc_cli_path = lhc_cli_path
        
        # thread vars
        self.thread_lock = threading.Lock()
        self.thread_LHC = None
        self.last_LHC_response = None

    def execute_protocol(self, protocol_name):
        # Only allow one LHC thread running
        self.thread_lock.acquire()
        try:
            if self.is_LHC_ready():
                # Start a thread
                self.thread_LHC = threading.Thread(target=self.execute_protocol_threaded, args=([protocol_name]))
                self.thread_LHC.start()
                response = [{"status": "OK",
                            "value": "",
                            "details": "Executed protocol in background thread"}]
            else:
                # throw error:
                response = [{"status": "WARNING",
                            "value": "",
                            "details": "LHC is busy - will not run command"}]
                logging.warning(response)

        except Exception as e:
            logging.error(traceback.format_exc())
            logging.error(e)
            response = [{"status": "ERROR",
                        "value": "",
                        "details": "See log for traceback"}]
            
        finally:
            self.thread_lock.release()
            logging.debug('Done finally')
            return json.dumps(response)


    def execute_protocol_threaded(self, protocol_name):
        logging.info("Inside execute_protocol_threaded, protocol_name=" + protocol_name)

        try:
            protocol_path = os.path.join(self.protocols_root, protocol_name)        
            logging.info("protocol_path=" + protocol_path)

            #
            # Execute on server and set response
            #
            proc_out = subprocess.Popen([self.lhc_cli_path,
                                    self.product_name,
                                    self.com_port,
                                    "LHC_RunProtocol",
                                    protocol_path
                                    ],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT
                                    )
            stdout,stderr = proc_out.communicate()

            self.last_LHC_response = stdout.decode("utf-8")

        except Exception as e:
            logging.error("Error in execute_protocol_threaded")
            logging.error(traceback.format_exc())
            logging.error(e)
            
        finally:
            logging.info('last_LHC_response' + str(self.last_LHC_response))
            logging.info('Finished Thread')

    def is_ready(self):
        logging.debug("Inside is_ready")
        is_ready = self.is_LHC_ready()
        response = [{"status": "OK",
                    "value": is_ready,
                    "details": ""}]
        return json.dumps(response)

    def get_last_LHC_response(self):
        logging.debug("Inside get_last_LHC_response")
        response = [{"status": "OK",
                    "value": self.last_LHC_response,
                    "details": ""}]
        return json.dumps(response)

    def is_LHC_ready(self):
        if self.thread_LHC is None or self.thread_LHC.is_alive() == False:
            return True
        else:
            return False


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
    # http://http://localhost:5050/execute_protocol/_FOR_anders/dispenser_prime_all_buffers.LHC
    # http://localhost:5050/last_LHC_response
    # http://localhost:5050/is_ready
    #
