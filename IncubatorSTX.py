#!/usr/bin/env python3
import logging
import socket
import time
import threading
#import os.path
import traceback
from flask import Flask, json
from flask import jsonify

RETCODE_STX2RESET_OK = ""
RETCODE_DESCR_STX2RESET = """
    Return values: CR+LF.
"""

RETCODE_STX2WRITESETCLIMATE_OK = ""
RETCODE_DESCR_STX2WRITESETCLIMATE = """
    Return values: CR+LF.
"""

RETCODE_STX2ACTIVATE_OK = "1"
RETCODE_DESCR_STX2ACTIVATE = """
    Return values: the reply consists of one or two characters (separated by
    semicolon) and CR+LF.
    The first character is the device initialisation state:
    1 - Communication is opened and device is initialised.
    -1 - Error of opening Serial Port.
    -2 - Error of opening Serial Port (serial Port is already opened).
    -3 - No communication.
    -4 - Communication Error.
    -5 - System Error (System Error Flag is true).
    -6 - User Door is opened (or cannot read User Door status).
    -7 – User Door is unlocked or cannot lock a User Door (available if
    door lock option present).
    The second character depends on Barcode Reader presence and shows it
    initialisation state :
    1 - BCR Serial Port is successfully opened.
    -1 - Error of opening BCR port.
    -2 - Wrong value of BCR port.
"""

RETCODE_STX2SERVICEMOVEPLATE_OK = "1"
RETCODE_DESCR_STX2SERVICEMOVEPLATE = """
    Returning values because of parameters error:
    -1 – Previous long operation is not finished.
    -2 - One of input parameters is not a valid integer value.
    -3 – A Source or a Target Device is not specified or not initialised.
    -4 - One or more of devices is not defined in a system.
    -5 – One of transport slot is not specified.
    -6 - Wrong value of a target transport slot.
    -7 - Wrong value of a source transport slot.
    -8 – Wrong value of a source position.
    -9 – Wrong value of a target position.

    Returning values because of internal device error:
    -ID;1 - Error during LoadPlate operation, device "ID".
    -ID;2 - Error during UnloadPlate operation.
    -ID;3 - Error during PickPlate operation.
    -ID;4 - Error during PlacePlate operation.
    -ID;5 - Error during SetPlate operation.
    -ID;6 - Error during GetPlate operation.
    -ID;7 – Device is not Ready
    -ID;8 – Device Status Error
"""

class IncubatorSTX:

    def __init__(self, id, host, port):
        logging.debug("Inside init")
        self.id = id
        self.host = host
        self.port = port

        # thread vars
        self._synchronization_lock = threading.Lock()
        self._thread_STX = None
        self._last_STX_response = None

    def _create_ok_response(self, method):
        response = {"status": "OK",
                    "value": "",
                    "method": method,
                    "details": ""}
        logging.debug("response:" + str(response))
        return response

    def _create_error_response(self, method, value, description):
        logging.debug("value:" + str(value))
        logging.debug("description:" + str(description))
        response = {"status": "ERROR",
                    "value": str(value),
                    "method": method,
                    "details": description}
        logging.debug("response:" + str(response))
        return response

    def _movePlateFromCassetteToShovel(self, nCassette, nLevel): 
        id = self.id
        self._stx2ServiceMovePlate(id,2,nCassette,nLevel,1,1,id,3,0,0,1,1)

    def _movePlateFromShovelToCassette(self, nCassette, nLevel): 
        id = self.id
        self._stx2ServiceMovePlate(id,3,0,0,1,1,id,2,nCassette,nLevel,1,1)

    def _movePlateFromTransferStationToShovel(self): 
        id = self.id
        self._stx2ServiceMovePlate(id,1,0,0,1,1,id,3,0,0,1,1) 
    
    def _movePlateFromShovelToTransferStation(self): 
        id = self.id
        self._stx2ServiceMovePlate(id,3,0,0,1,1,id,1,0,0,1,1) 
    
    def _movePlateFromTransferStationToCassette(self, nCassette, nLevel):
        id = self.id
        self._stx2ServiceMovePlate(id,1,0,0,1,1,id,2,nCassette,nLevel,1,1)
    
    def _movePlateFromCassetteToTransferStation(self, nCassette, nLevel):
        id = self.id
        self._stx2ServiceMovePlate(id,2,nCassette,nLevel,1,1,id,1,0,0,1,1)
    
    def _movePlateFromCassetteToCassette(self, nCassette, nLevel, nToCassette, nToLevel):
        id = self.id
        self._stx2ServiceMovePlate(id,2,nCassette,nLevel,1,1,id,2,nToCassette,nToLevel,1,1)
    

    def _stx2ServiceMovePlate(self, srcID, srcPos, srcSlot, srcLevel, transSrcSlot, srcPlType,
                                   trgID, trgPos, trgSlot, trgLevel, transTrgSlot, trgPlType):
        logging.debug("Inside _stx2ServiceMovePlate")

        # SrcInstr     - Identifier of a source Device.
        # SrcPos       - Source position {1-TransferStation, 2-Slot-Level
        #                Position,3 – Shovel, 4-Tunnel, 5-Tube Picker}.
        # SrcSlot      - plate slot position of source.
        # SrcLevel     - plate Level position of source.
        # TransSrcSlot – (not relevant for us)
        # SrcPlType    - Type of plate of source position {0-MTP, 1-DWP, 3-P28}

        cmd = (f"STX2ServiceMovePlate({srcID},{srcPos},{srcSlot},{srcLevel},{transSrcSlot},{srcPlType},"
                                    f"{trgID},{trgPos},{trgSlot},{trgLevel},{transTrgSlot},{trgPlType})\r"
        )

        retval = self._sendCmd(cmd)
        if retval == RETCODE_STX2SERVICEMOVEPLATE_OK:
            response = self._create_ok_response("_stx2ServiceMovePlate")
        else:
            response = self._create_error_response("_stx2ServiceMovePlate", retval, RETCODE_DESCR_STX2SERVICEMOVEPLATE)

        self._last_STX_response = response


    def _stx2GetSysStatus(self):
        logging.debug("Inside _stx2GetSysStatus")
        cmd = "STX2GetSysStatus(" + self.id + ")\r"
        retval = self._sendCmd(cmd)

    def _stx2Inventory(self):
        # Inventory file will be saved on STX-server in directory of jSTXDriver.jar
        logging.debug("Inside _stx2Inventory")
        cmd = "STX2Inventory(" + self.id + ",,0,0)\r"
        retval = self._sendCmd(cmd)

    def _stx2Reset(self):
        logging.debug("Inside _stx2Reset")
        cmd = "STX2Reset(" + self.id + ")\r"
        retval = self._sendCmd(cmd)
        if retval == RETCODE_STX2RESET_OK:
            response = self._create_ok_response("_stx2Reset")
        else:
            response = self._create_error_response("_stx2Reset", retval, RETCODE_DESCR_STX2RESET)

        return response

    def _stx2Activate(self):
        logging.debug("Inside _stx2Activate")
        cmd = "STX2Activate(" + self.id + ")\r"
        retval = self._sendCmd(cmd)
        if retval == RETCODE_STX2ACTIVATE_OK:
            response = self._create_ok_response("_stx2Activate")
        else:
            response = self._create_error_response("_stx2Activate", retval, RETCODE_DESCR_STX2ACTIVATE)

        return response

    def _stx2IsOperationRunning(self):
        logging.debug("Inside _stx2IsOperationRunning")
        cmd = "STX2IsOperationRunning(" + self.id + ")\r"
        retval = self._sendCmd(cmd)

    
    def _stx2ReadActualClimate(self):
        logging.debug("Inside _stx2ReadActualClimate")
        cmd = "STX2ReadActualClimate(" + self.id + ")\r"
        retval = self._sendCmd(cmd)
        return retval

    def _stxReadSetClimate(self):
        logging.debug("Inside _stxReadSetClimate")
        cmd = "STX2ReadSetClimate(" + self.id + ")\r"
        retval = self._sendCmd(cmd)
        return retval
    def _stxWriteSetClimate(self, temp, humid, co2, n2):
        logging.debug("Inside _stxWriteSetClimate")

        cmd = f"STX2WriteSetClimate({self.id},{temp},{humid},{co2},{n2})\r"
        retval = self._sendCmd(cmd)
        if retval == RETCODE_STX2WRITESETCLIMATE_OK:
            response = self._create_ok_response("_stxWriteSetClimate")
        else:
            response = self._create_error_response("_stxWriteSetClimate", retval, RETCODE_DESCR_STX2WRITESETCLIMATE)
        return response


    def resetAndActivate(self):
        logging.debug("Inside resetAndActivate")

        try:
            # Dont worry if stx2Reset failed or not
            unused_response = self._stx2Reset()
            response = self._stx2Activate()

            # No error was thrown so Clear last response
            self._clearLastStxResponse()

        except Exception as e:
            logging.error(traceback.format_exc())
            logging.error(e)
            response = [{"status": "ERROR",
                        "value": "",
                        "details": "See log for traceback"}]
            
        finally:
            logging.debug('Done finally')
            return jsonify(response)

    def is_ready(self):
        logging.debug("Inside is_ready")

        if self._is_STX_errored():
            response = {"status": "ERROR",
                        "value": False,
                        "details": self._last_STX_response}
        else:
            is_ready = not self._is_STX_busy()
            response = {"status": "OK",
                        "value": is_ready,
                        "details": ""}
        return jsonify(response)

    def _is_STX_ready(self):
        logging.debug("Inside _is_STX_ready")

        if self._is_STX_busy() or self._is_STX_errored():
            return False
        else:
            return True

    def _is_STX_busy(self):
        if self._thread_STX is None or self._thread_STX.is_alive() == False:
            return False
        else:
            return True

    def _is_STX_errored(self):
        is_errored = False
        if self._last_STX_response is not None:
            if self._last_STX_response.get("status") == "ERROR":
                is_errored = True
        return is_errored

    def getClimate(self):
        logging.debug("Inside getClimate")
        response = self._stx2ReadActualClimate()

        splitted = response.split(";")
        climate = {
            "temp": splitted[0],
            "humid": splitted[1],
            "co2": splitted[2],
            "n2": splitted[3]
        }
        logging.debug("climate:" + str(climate))

        response = {"status": "OK",
                    "value": climate,
                    "details": ""}
        return jsonify(response)

        return response
    
    def getPresetClimate(self):
        logging.debug("Inside getPresetClimate")
        response = self._stxReadSetClimate()

        splitted = response.split(";")
        climate = {
            "temp": splitted[0],
            "humid": splitted[1],
            "co2": splitted[2],
            "n2": splitted[3]
        }
        logging.debug("presetclimate:" + str(climate))

        response = {"status": "OK",
                    "value": climate,
                    "details": ""}
        return jsonify(response)

        return response
    
    def setPresetClimate(self, temp, humid, co2, n2):
        logging.debug("Inside setPresetClimate")

        try:
            response = self._stxWriteSetClimate(temp, humid, co2, n2)

        except Exception as e:
            logging.error(traceback.format_exc())
            logging.error(e)
            response = [{"status": "ERROR",
                        "value": "",
                        "details": "See log for traceback"}]
            
        finally:
            logging.debug('Done finally')
            return jsonify(response)


    def outputPlate(self, nPos):
        logging.debug("Inside outputPlate, nPos= " + str(nPos))


        # position 0-21  is cassette 1 level 1-22
        # position 22-43 is cassette 2 level 1-22
        nCassette = 1 + int(nPos / 22)
        nLevel = 1 + (nPos % 22)

        # Synchronize the check_if_ready and execution of thread to avoid race between check and execution
        self._synchronization_lock.acquire()
        try:
            if self._is_STX_ready():

                logging.debug("self._is_STX_ready()" + str(self._is_STX_ready()))

                self._thread_STX = threading.Thread(target=self._movePlateFromCassetteToTransferStation, args=([nCassette, nLevel]))
                self._thread_STX.start()
                response = {"status": "OK",
                        "value": "",
                        "details": "Executed protocol in background thread"}

            else:

                # send warning:
                response = {"status": "WARNING",
                            "value": "",
                            "details": "Incubator is not ready - will not run command"}
                logging.warning(response)

        except Exception as e:
            logging.error(traceback.format_exc())
            logging.error(e)
            response = [{"status": "ERROR",
                        "value": "",
                        "details": "See log for traceback"}]
            
        finally:
            logging.debug('Done finally outputPlate')
            self._synchronization_lock.release()
            return jsonify(response)


    def inputPlate(self, nPos):
        logging.debug("Inside inputPlate, nPos= " + str(nPos))


        # position 0-21  is cassette 1 level 1-22
        # position 22-43 is cassette 2 level 1-22
        nCassette = 1 + int(nPos / 22)
        nLevel = 1 + (nPos % 22)

        # Synchronize the check_if_ready and execution of thread to avoid race between check and execution
        self._synchronization_lock.acquire()
        try:
            if self._is_STX_ready():

                self._thread_STX = threading.Thread(target=self._movePlateFromTransferStationToCassette, args=([nCassette, nLevel]))
                self._thread_STX.start()
                response = {"status": "OK",
                        "value": "",
                        "details": "Executed protocol in background thread"}

            else:

                # send warning:
                response = {"status": "WARNING",
                            "value": "",
                            "details": "Incubator is not ready - will not run command"}
                logging.warning(response)

        except Exception as e:
            logging.error(traceback.format_exc())
            logging.error(e)
            response = [{"status": "ERROR",
                        "value": "",
                        "details": "See log for traceback"}]
            
        finally:
            logging.debug('Done finally inputPlate')
            self._synchronization_lock.release()
            return jsonify(response)

    def _clearLastStxResponse(self):
        self._last_STX_response = None

    def get_last_STX_response(self):
        logging.debug("Inside get_last_STX_response")
        response = {"status": "OK",
                    "value": self._last_STX_response,
                    "details": ""}
        return jsonify(response)



    def _sendCmd(self, cmd):
        logging.debug("Inside sendCmd")
        logging.debug("cmd:" + str(cmd))
        RECIEVE_BUFFER_SIZE = 8192 # Also max response length since we are not looping response if buffer gets full
        
        # convert cmd to bytes
        cmd_as_bytes = bytes(cmd, "ascii")

        # send and recieve
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.host, self.port))
        s.sendall(cmd_as_bytes)
        recieved = s.recv(RECIEVE_BUFFER_SIZE)
        logging.debug("Received: " + repr(recieved))
        s.close()

        # decode recieved byte array to ascii
        response = recieved.decode('ascii')
        response = response.strip()
 
        return response


if __name__ == '__main__':


    #
    # Configure logging
    #
    logging.basicConfig(format='%(asctime)s,%(msecs)d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s',
                        datefmt='%H:%M:%S',
                        level=logging.DEBUG)

    rootLogger = logging.getLogger()

    server = Flask(__name__)
    
    incu = IncubatorSTX("STX", "130.238.44.60", 3333)

    incu.resetAndActivate()
    #incu.stx2Reset()
    #incu.stx2Activate()
    #incu.getClimate()
    #incu.movePlateFromCassetteToShovel(1,3)
    #incu.movePlateFromTransferStationToShovel()
    #incu.movePlateFromShovelToCassette(2,2)
    #incu.movePlateFromCassetteToCassette(1,3,2,10)
    #incu.movePlateFromShovelToTransferStation()
    #incu.movePlateFromTransferStationToShovel()
    #incu.movePlateFromShovelToCassette(1,3)
    #incu.movePlateFromShovelToTransferStation()
    #incu.stx2Inventory()
    #incu.stx2GetSysStatus()
    #time.sleep(4)
    #incu.stx2Inventory()
    #time.sleep(4)
    #incu.stx2IsOperationRunning()
    #incu.stx2GetSysStatus()
    #incu.outputPlate(31)
    #incu.inputPlate(20)
    incu.inputPlate(22)
    #incu.inputPlate(18)

