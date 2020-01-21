#!/usr/bin/env python3
import connexion
import logging
import subprocess
import sys

from connexion import NoContent


def execute_protocol(protocol_name):

  logging.info("Inside execute_protocol, protocol_name=" + protocol_name)

  #
  # Execute on server an then return response
  #
  proc_out = subprocess.Popen(["C:\Program Files (x86)\BioTek\Liquid Handling Control 2.22\LHC_CallerCLI.exe", "LHC_SetProductName", "MultiFloFX"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT)
  stdout,stderr = proc_out.communicate()

  response = stdout

  return response

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

  logging.info("Inside status")

  #
  # Execute on server an then return response
  #
  stdout = "Ready"

  #
  # Maybe parse stdout
  #
  response = "Ready"

  return response



if __name__ == '__main__':
    # Testrun
    retval = is_ready()
    print(str(retval))



