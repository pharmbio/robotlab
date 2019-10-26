#!/usr/bin/env python3
import connexion
import logging

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
  stdout = "Bla bla OK"

  #
  # Maybe parse stdout
  #
  response = "OK"

  return response

def execute_no2():

  logging.info("Inside execute_no2")

  #
  # Execute on server an then return response
  #
  stdout = "Bla bla OK"

  #
  # Maybe parse stdout
  #
  response = "OK"

  return response

