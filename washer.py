#!/usr/bin/env python3
import connexion
import logging
import subprocess
import sys

from connexion import NoContent


def execute_prog(prog_id):

  logging.info("Inside execute_prog, prog_id=" + prog_id)

  #
  # Execute on server an then return response
  #
  stdout = "Bla bla OK"

  #
  # Maybe parse stdout
  #
  response = "OK"

  return response

def execute_no1():

  logging.info("Inside execute_no1")
  
  #
  # Execute on server an then return response
  #
  proc_out = subprocess.Popen(["C:\Program Files (x86)\BioTek\Liquid Handling Control 2.22\LHC_CallerCLI.exe", "LHC_SetProductName", "MultiFloFX"], 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT)
  stdout,stderr = proc_out.communicate()

  response = stdout

  return response

def execute_no2():

  logging.info("Inside execute_no2")

  #
  # Execute on server an then return response
  #
  cLHC = ClassLHCRunner()
  productName = "MultiFloFX"
  nRetCode = cLHC.LHC_SetProductName(productName)


  response = "RetVal=" + str(nRetCode)

  return response
  
  
  
if __name__ == '__main__':
    # Testrun
    retval = execute_no2()
    print(str(retval))
  


