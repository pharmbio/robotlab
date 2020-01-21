#!/usr/bin/env python3
import connexion
import logging
import subprocess
import sys

from connexion import NoContent

def status():

  logging.info("Inside status")

  #
  # Execute on server an then return response
  #
  stdout = "Bla bla OK"

  #
  # Maybe parse stdout
  #
  response = "OK"

  return response


def is_ready():

  logging.info("Inside is_ready")

  #
  # Execute on server an then return response
  #
  stdout = "Ready"

  #
  # Maybe parse stdout
  #
  response = "Ready"

  return response


def start():

  logging.info("Inside start")

  #
  # Execute on server an then return response
  #
  stdout = "OK"

  #
  # Maybe parse stdout
  #
  response = "OK"

  return response


def stop():

  logging.info("Inside stop")

  #
  # Execute on server an then return response
  #
  stdout = "OK"

  #
  # Maybe parse stdout
  #
  response = "OK"

  return response





if __name__ == '__main__':
    # Testrun
    retval = is_ready()
    print(str(retval))



