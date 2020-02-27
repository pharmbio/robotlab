#!/usr/bin/env python3
import logging
import subprocess
import sys
import os.path
import threading
import traceback
from flask import Flask, json

#
# http://localhost:5050/execute_protocol/dispenser_prime_all_buffers.LHC
# http://localhost:5050/last_LHC_response
# http://localhost:5050/is_ready
#

# constants
BIOTEK_PRODUCT = "MultiFloFX"
COM_PORT = "USB MultiFloFX sn:19041612"
PROTOCOLS_ROOT = "C:\\ProgramData\\BioTek\\Liquid Handling Control 2.22\\Protocols"
LHC_CALLER_CLI_PATH = "C:\\Program Files (x86)\\BioTek\\Liquid Handling Control 2.22\\LHC_CallerCLI.exe"

# thread vars
thread_lock = threading.Lock()
thread_LHC = None
last_LHC_response = None

# restserver
PORT = 5050
api = Flask(__name__)


@api.route('/is_ready', methods=['GET'])
def is_ready():

    logging.debug("Inside is_ready")
    is_ready = is_LHC_ready()
    response = [{"status": "OK",
                "value": is_ready,
                "details": ""}]
    return json.dumps(response)

@api.route('/last_LHC_response', methods=['GET'])
def get_last_LHC_response():

    logging.debug("Inside get_last_LHC_response")
    response = [{"status": "OK",
                "value": last_LHC_response,
                "details": ""}]
    return json.dumps(response)

@api.route('/execute_protocol/<path:protocol_name>', methods=['GET'])
def execute_protocol(protocol_name):

    global thread_LHC
    
    # Only allow one LHC thread running
    thread_lock.acquire()
    try:
        if is_LHC_ready():
            # Start a thread
            thread_LHC = threading.Thread(target=execute_protocol_threaded, args=([protocol_name]))
            thread_LHC.start()
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
        thread_lock.release()
        logging.debug('Done finally')
        return json.dumps(response)


def execute_protocol_threaded(protocol_name):

    global last_LHC_response

    logging.info("Inside execute_protocol_threaded, protocol_name=" + protocol_name)
    
    try:
        protocol_path = os.path.join(PROTOCOLS_ROOT, protocol_name)
        
        logging.info("protocol_path=" + protocol_path)

        #
        # Execute on server and set response
        #
        proc_out = subprocess.Popen([LHC_CALLER_CLI_PATH,
                                BIOTEK_PRODUCT,
                                COM_PORT,
                                "LHC_RunProtocol",
                                protocol_path
                                ],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT
                                )
        stdout,stderr = proc_out.communicate()

        last_LHC_response = stdout.decode("utf-8")

    except Exception as e:
        logging.error("Error in execute_protocol_threaded")
        logging.error(traceback.format_exc())
        logging.error(e)
        
    finally:
        logging.info('last_LHC_response' + str(last_LHC_response))
        logging.info('Finished Thread')

def is_LHC_ready():
    if thread_LHC is None or thread_LHC.is_alive() == False:
        return True
    else:
        return False


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    logging.info("Before start server, port=" + str(PORT))
    api.run(port=PORT)
