#!/usr/bin/env python3
import logging
import socket
import time
#import os.path
#import traceback
#from flask import Flask, json
#from flask import jsonify

ERROR_CODES_MOVE = """
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

class Incubator:

    def __init__(self, id, host, port):
        logging.debug("Inside init")
        self.id = id
        self.host = host
        self.port = port


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

        response = self._sendCmd(cmd)
        if response != "1":
            logging.error("Error codes: \n" + ERROR_CODES_MOVE)
            raise Exception("_stx2ServiceMovePlate response error: " + response)


    def _stx2GetSysStatus(self):
        logging.debug("Inside _stx2GetSysStatus")
        cmd = "STX2GetSysStatus(" + self.id + ")\r"
        response = self._sendCmd(cmd)

    def _stx2Inventory(self):
        # Inventory file will be saved on STX-server in directory of jSTXDriver.jar
        logging.debug("Inside _stx2Inventory")
        cmd = "STX2Inventory(" + self.id + ",,0,0)\r"
        response = self._sendCmd(cmd)

    def _stx2Reset(self):
        logging.debug("Inside _stx2Reset")
        cmd = "STX2Reset(" + self.id + ")\r"
        response = self._sendCmd(cmd)

    def _stx2Activate(self):
        logging.debug("Inside _stx2Activate")
        cmd = "STX2Activate(" + self.id + ")\r"
        response = self._sendCmd(cmd)
        if response != "1":
            raise Exception("_stx2Activate response error: " + response)

    def _stx2IsOperationRunning(self):
        logging.debug("Inside _stx2IsOperationRunning")
        cmd = "STX2IsOperationRunning(" + self.id + ")\r"
        response = self._sendCmd(cmd)
        if response == "-1":
            raise Exception("_stx2IsOperationRunning response error: " + response)
        return response
    
    def _stx2ReadActualClimate(self):
        logging.debug("Inside _stx2ReadActualClimate")
        cmd = "STX2ReadActualClimate(" + self.id + ")\r"
        response = self._sendCmd(cmd)

        return response

    def resetAndAcrivate(self):
        logging.debug("Inside resetAndAcrivate")
        
        


    def getClimate(self):
        logging.debug("Inside getClimate")
        cmd = "STX2ReadActualClimate(" + self.id + ")\r"
        response = self._stx2ReadActualClimate()

        splitted = response.split(";")
        climate = {
            "temp": splitted[0],
            "humid": splitted[1],
            "co2": splitted[2],
            "n2": splitted[3]
        }
        logging.debug("climate:" + str(climate))

        return climate

    def outputPlate(self, nPos):
        logging.debug("Inside outputPlate, nPos= " + str(nPos))

        # position 0-21  is cassette 1 level 1-22
        # position 22-43 is cassette 2 level 1-22

        nCassette = 1 + int(nPos / 22)
        nLevel = 1 + (nPos % 22)

        self._movePlateFromCassetteToTransferStation(nCassette, nLevel)


    def inputPlate(self, nPos):
        logging.debug("Inside inputPlate, nPos= " + str(nPos))

        # position 0-21  is cassette 1 level 1-22
        # position 22-43 is cassette 2 level 1-22

        nCassette = 1 + int(nPos / 22)
        nLevel = 1 + (nPos % 22)

        self._movePlateFromTransferStationToCassette(nCassette, nLevel)


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
    
    incu = Incubator("STX", "130.238.44.60", 3333)

    incu.stx2Reset()
    incu.stx2Activate()
    incu.getClimate()
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
