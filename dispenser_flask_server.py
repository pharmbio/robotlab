#!/usr/bin/env python3
import logging
import subprocess
import sys
import os.path
import threading
from flask import Flask, json

LHC_CALLER_CLI_PATH = "C:\Program Files (x86)\BioTek\Liquid Handling Control 2.22\LHC_CallerCLI.exe"
BIOTEK_PRODUCT = "MultiFloFX"
COM_PORT = "USB MultiFloFX sn:19041612"
PROTOCOLS_ROOT = "C:\ProgramData\BioTek\Liquid Handling Control 2.22\Protocols\_FOR_anders"

# define restserver and api
api = Flask(__name__)

# thread vars
lock = threading.Lock()
LHC_thread = None

@api.route('/execute_protocol/<protocol_file>', methods=['GET'])
def execute_protocol(protocol_file):
    # define globals
    global lock
    global LHC_thread
    
    lock.acquire()
    try:
        if LHC_thread is None or LHC_thread.is_alive() == False:
            # Start a thread
            LHC_thread = threading.Thread(target=execute_protocol_threaded, args=([protocol_file]))
            LHC_thread.start()
            result = [{"execute": "done"}]
        else:
            # throw error:
            logging.error('Throw error here')
            result = [{"error": "busy"}]
    except Exception as e:
        print(traceback.format_exc())
        logging.error(e)
        result = [{"execute": "error"}]
        
    finally:
        lock.release()
        logging.debug('Inside finally')
        
  
    return json.dumps(result)


def execute_protocol_threaded(protocol):
    logging.info("Inside execute_protocol, protocol_name=" + protocol)
    
    protocol_path = os.path.join(PROTOCOLS_ROOT, protocol)
    
    logging.info("protocol_path=" + protocol_path)

    #
    # Execute on server an then return response
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

    response = stdout
    logging.info('Finished Thread')

@api.route('/is_ready', methods=['GET'])
def is_ready():
   
   global LHC_thread

   logging.info("Inside is_ready")
   
   if LHC_thread is None or LHC_thread.is_alive() == False:
     is_ready = True
   else:
     is_ready = False
     
   result = [{"is_ready": is_ready}]
  
   return json.dumps(result)


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    logging.info("Before start server")
    api.run(port=5050)

