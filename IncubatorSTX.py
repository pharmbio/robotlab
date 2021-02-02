#!/usr/bin/env python3
import logging
import socket
#import sys
#import os.path
#import traceback
#from flask import Flask, json
#from flask import jsonify


class Incubator:

    def __init__(self, id, host, port):
        logging.debug("Inside init")
        self.id = id
        self.host = host
        self.port = port

    def getCo2(self):
        logging.debug("Inside getCo2")
        cmd = "STX2ReadActualClimate(" + str(self.id) + ")"
        response = self.sendCmd(cmd)
        logging.info("response: " + str(response))
    
    def sendCmd(self, cmd):
        RECIEVE_BUFFER_SIZE = 8192 # Also max response length since we are not looping response if buffer gets full
        host = self.host
        port = self.port                  # The same port as used by the server
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((host, port))
        s.sendall(b'Hello, world')
        data = s.recv(RECIEVE_BUFFER_SIZE)
        s.close()
        print('Received', repr(data))

        return data


if __name__ == '__main__':
    # Init logging
    logging.basicConfig(level=logging.DEBUG)
    
    incu = Incubator("STX", "130.238.44.60", 3333)

    incu.getCo2()
    
