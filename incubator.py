#!/usr/bin/env python3
import connexion
import logging
import subprocess
import sys
import time

# Import client code
sys.path.append('/pharmbio/incubator-automation')
import incubator_client

from connexion import NoContent

def is_open():

  logging.info("Inside is_open")

  #
  # Execute on server an then return response
  #
  is_open = incubator_client.is_open()

  response = {"status": is_open,
              "value": "",
              "details": ""}

  return response

def is_closed():

  logging.info("Inside is_closed")

  #
  # Execute on server an then return response
  #
  is_closed = incubator_client.is_closed()

  response = {"status": is_closed,
              "value": "",
              "details": ""}

  return response


def open():

  logging.info("Inside open")
  incubator_client.open()

  response = {"status": "OK",
              "value": "",
              "details": ""}

  return response


def close():

  logging.info("Inside close")
  incubator_client.close()

  response = {"status": "OK",
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
    retval = open()
    print("open:" + str(retval))

    time.sleep(2000)

    retval = is_open()
    print("is_open:" + str(retval))

    time.sleep(2000)

    retval = is_open()
    print("is_open:" + str(retval))

    time.sleep(2000)

    retval = is_open()
    print("is_open:" + str(retval))

    retval = close()
    print("close:" + str(retval))

    time.sleep(2000)

    retval = is_closed()
    print("is_closed:" + str(retval))

    time.sleep(2000)

    retval = is_closed()
    print("is_closed:" + str(retval))

    time.sleep(2000)

    retval = is_closed()
    print("is_closed:" + str(retval))


    time.sleep(2000)

    retval = is_closed()
    print("is_closed:" + str(retval))

    print("done:")





