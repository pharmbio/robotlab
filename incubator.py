#!/usr/bin/env python3
import connexion
import logging
import subprocess
import sys
import time

# Import client code
#sys.path.append('/pharmbio/shaker-robot')
#import shaker_client

from connexion import NoContent

def status():

  logging.info("Inside status")

  #
  # Execute on server an then return response
  #

  # status = shaker_client.getStatus()
  status = "OPEN"

  response = {"status": status,
              "value": "",
              "details": ""}

  return response


def is_ready():

  logging.info("Inside is_ready")
  status_response = status()

  if(status_response['status'] == 'OPEN'):
    response = {"status": 'True',
                "value": "",
                "details": ""}
  else:
    response = {"message": 'False',
                "value": "",
                "details": ""}
  
  return response


def open():

  logging.info("Inside open")

  #retval = shaker_client.startShaker()
  retval = "OK"

  response = {"status": retval,
              "value": "",
              "details": ""}

  return response


def close():

  logging.info("Inside close")
  
  #retval = shaker_client.stopShaker()
  retval = "OK"

  response = {"status": retval,
              "value": "",
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





