#!/usr/bin/env python3
import connexion
import logging
import subprocess
import sys
import time

# Import shaker client
sys.path.append('/pharmbio/shaker-robot')
import shaker_client

from connexion import NoContent

def status():

  logging.info("Inside status")

  #
  # Execute on server an then return response
  #
  status = shaker_client.getStatus()

  response = {"message": status,
              "details": ""}

  return response


def is_ready():

  logging.info("Inside is_ready")
  status_response = status()

  if(status_response['message'] == 'READY'):
    response = {"message": 'True',
                "details": ""}
  else:
    response = {"message": 'False',
                "details": ""}
  
  return response


def start():

  logging.info("Inside start")
  retval = shaker_client.startShaker()

  response = {"message": retval,
              "details": ""}

  return response


def stop():

  logging.info("Inside stop")
  retval = shaker_client.stopShaker()

  response = {"message": retval,
              "details": ""}

  return response


if __name__ == '__main__':
    #
    # Configure logging
    #
    logging.basicConfig(format='%(asctime)s,%(msecs)d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s',
                            datefmt='%H:%M:%S',
                            level=logging.INFO)

    # Testrun
    retval = is_ready()
    print("is_ready:" + str(retval))

    retval = status()
    print("status:" + str(retval))

    retval = start()
    print("start:" + str(retval))

    retval = start()
    print("start:" + str(retval))

    retval = status()
    print("status:" + str(retval))

    time.sleep(1)

    retval = status()
    print("status:" + str(retval))

    retval = stop()
    print("start:" + str(retval))

    time.sleep(3)

    retval = status()
    print("status:" + str(retval))

    retval = stop()
    print("start:" + str(retval))





