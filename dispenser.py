#!/usr/bin/env python3
import connexion
import logging
import subprocess
import sys

from connexion import NoContent

LHC_CALLER_CLI_PATH = "C:\Program Files (x86)\BioTek\Liquid Handling Control 2.22\LHC_CallerCLI.exe"
BIOTEK_PRODUCT = "MultiFloFX"
COM_PORT = "USB MultiFloFX sn:19041612"


def execute_protocol(protocol_file):

  logging.info("Inside execute_protocol, protocol_name=" + protocol_file)

  #
  # Execute on server an then return response
  #
  proc_out = subprocess.Popen([LHC_CALLER_CLI_PATH,
                               BIOTEK_PRODUCT,
                               COM_PORT,
                               "LHC_RunProtocol",
                               protocol_file
                               ],
                               stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT
                              )
  stdout,stderr = proc_out.communicate()

  response = stdout

  return response

def status():

  logging.info("Inside status")

  #
  # Execute on server an then return response
  #
  proc_out = subprocess.Popen([LHC_CALLER_CLI_PATH,
                               BIOTEK_PRODUCT,
                               COM_PORT,
                               "LHC_GetProtocolStatus"
                               ],
                               stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT
                              )
  stdout,stderr = proc_out.communicate()

  response = stdout

  return response


def is_ready():

  logging.info("Inside is_ready")

  #
  # Execute on server an then return response
  #
  stdout = "???"

  #
  # Maybe parse stdout
  #
  response = "Ready"

  return response

#this.timerStatus.Interval = 500;
#this.timerStatus.Tick += new System.EventHandler(this.timerStatus_Tick);


if __name__ == '__main__':
    # Testrun
    retval = status()
    print(str(retval))
    
    retval = execute_protocol("C:\ProgramData\BioTek\Liquid Handling Control 2.22\Protocols\_FOR_anders\dispenser_prime_all_buffers.LHC")
    print(str(retval))



