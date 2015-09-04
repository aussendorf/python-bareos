#!/usr/bin/env python

"""
Low Level socket methods to communication with the bareos-director.
"""

# Authentication code is taken from
# https://github.com/hanxiangduo/bacula-console-python

from   bareos.exceptions import *
from   bareos.util.bareosbase64 import BareosBase64
from   bareos.util.password import Password
from   bareos.bsock.constants import Constants
from   bareos.bsock.protocolmessages import ProtocolMessages
import hmac
import logging
import random
import socket
import struct
import time

class LowLevel(object):
    """
    Low Level socket methods to communicate with the bareos-director.
    """

    def __init__(self):
        self.logger = logging.getLogger()
        self.logger.debug("init")
        self.status = None
        self.address = None
        self.password = None
        self.port = None
        self.dirname = None
        self.socket = None


    def connect(self, address="localhost", port=9101, dirname=None):
        '''
        connect to bareos-director
        '''
        self.address = address
        self.port = port
        if dirname:
            self.dirname = dirname
        else:
            self.dirname = address
        try:
            self.socket = socket.create_connection((self.address, self.port))
        except socket.gaierror as e:
            self._handleSocketError(e)
            raise ConnectionError(
                "failed to connect to host " + str(self.address) + ", port " + str(self.port) + ": " + str(e))
        else:
            self.logger.debug("connected to " + str(self.address) + ":" + str(self.port))


    def auth(self, password, clientname="*UserAgent*"):
        '''
        login to the bareos-director
        if the authenticate success return True else False
        dir: the director location
        clientname: own name. Default is *UserAgent*
        '''
        if not isinstance(password, Password):
            raise AuthenticationError("password must by of type bareos.Password() not %s" % (type(password)))
        bashed_name = ProtocolMessages.hello(clientname)
        # send the bash to the director
        self.send(bashed_name)

        (ssl, result_compatible, result) = self._cram_md5_respond(password=password.md5(), tls_remote_need=0)
        if not result:
            raise AuthenticationError("failed respond")
        if not self._cram_md5_challenge(clientname=clientname, password=password.md5(), tls_local_need=0, compatible=True):
            raise AuthenticationError("failed challenge")
        return True


    def disconnect(self):
        ''' disconnect '''
        # TODO
        pass


    def send(self, msg=None):
        '''use socket to send request to director'''
        if self.socket == None:
            raise RuntimeError("should connect to director first before send data")
        msg_len = len(msg) # plus the msglen info

        try:
            # convert to network flow
            self.socket.sendall(struct.pack("!i", msg_len) + msg)
            self.logger.debug("%s" %(msg.encode('string-escape')))
        except socket.error as e:
            self._handleSocketError(e)


    def recv(self):
        '''will receive data from director '''
        if self.socket == None:
            raise RuntimeError("should connect to director first before recv data")
        # first get the message length
        msg_header = self.socket.recv(4)
        if len(msg_header) <= 0:
            # perhaps some signal command
            raise RuntimeError("get the msglen error")
        # get the message
        msg_length = struct.unpack("!i", msg_header)[0]
        msg = ""
        if msg_length <= 0:
            self.logger.debug("msg len: " + str(msg_length))
        while msg_length > 0:
            msg += self.socket.recv(msg_length)
            msg_length -= len(msg)
        return msg


    def recv_msg(self):
        '''will receive data from director '''
        if self.socket == None:
            raise RuntimeError("should connect to director first before recv data")
        msg = ""
        submsg_length = 0
        try:
            while True:
                # first get the message length
                self.socket.settimeout(0.1)
                try:
                    header = self.socket.recv(4)
                except socket.timeout:
                    self.logger.debug("timeout on receiving header")
                else:
                    if len(header) == 0:
                        self.logger.debug("received empty header, assuming connection is closed")
                        break
                    elif len(header) < 0:
                        # perhaps some signal command
                        self.logger.error("failed to get header (len: " + str(len(header)) + ")")
                        raise RuntimeError("get the msglen error (" + str(len(header)) + ")")
                    else:
                        # get the message
                        submsg_length = struct.unpack("!i", header)[0]
                        if submsg_length <= 0:
                            self.__set_status(submsg_length)
                            if (submsg_length == Constants.BNET_EOD or
                                submsg_length == Constants.BNET_MAIN_PROMPT or
                                submsg_length == Constants.BNET_SUB_PROMPT):
                                    return msg
                        submsg = ""
                        while submsg_length > 0:
                            self.logger.debug("  submsg len: " + str(submsg_length))
                            self.socket.settimeout(None)
                            submsg += self.socket.recv(submsg_length)
                            submsg_length -= len(submsg)
                            msg += submsg
        except socket.error as e:
            self._handleSocketError(e)
        return msg


    def _cram_md5_challenge(self, clientname, password, tls_local_need=0, compatible=True):
        '''
        client launch the challenge,
        client confirm the dir is the correct director
        '''

        # get the timestamp
        # here is the console
        # to confirm the director so can do this on bconsole`way
        rand = random.randint(1000000000, 9999999999)
        #chal = "<%u.%u@%s>" %(rand, int(time.time()), self.dirname)
        chal = "<%u.%u@%s>" %(rand, int(time.time()), clientname)
        msg = 'auth cram-md5 %s ssl=%d\n' %(chal, tls_local_need)
        # send the confirmation
        self.send(msg)
        # get the response
        msg = self.recv().strip(chr(0))
        self.logger.debug("received: " + msg)

        # hash with password
        hmac_md5 = hmac.new(password)
        hmac_md5.update(chal)
        bbase64compatible = BareosBase64().string_to_base64(bytearray(hmac_md5.digest()), True)
        bbase64notcompatible = BareosBase64().string_to_base64(bytearray(hmac_md5.digest()), False)
        self.logger.debug("string_to_base64, compatible:     " + bbase64compatible)
        self.logger.debug("string_to_base64, not compatible: " + bbase64notcompatible)

        is_correct = ((msg == bbase64compatible) or (msg == bbase64notcompatible))
        # check against compatible base64 and Bareos specific base64
        if is_correct:
            self.send(ProtocolMessages.auth_ok())
        else:
            self.logger.error("expected result: %s or %s, but get %s" %(bbase64compatible, bbase64notcompatible, msg))
            self.send(ProtocolMessages.auth_failed())

        # check the response is equal to base64
        return is_correct

    def _cram_md5_respond(self, password, tls_remote_need=0, compatible=True):
        '''
        client connect to dir,
        the dir confirm the password and the config is correct
        '''
        # receive from the director
        chal = ""
        ssl = 0
        result = False
        msg = ""
        try:
            msg = self.recv()
        except RuntimeError:
            self.logger.error("RuntimeError exception in recv")
            return (0, True, False)
        # check the receive message
        self.logger.debug("(recv): " + msg.encode('string-escape'))
        msg_list = msg.split(" ")
        chal = msg_list[2]
        # get th timestamp and the tle info from director response
        ssl = int(msg_list[3][4])
        compatible = True
        # hmac chal and the password
        hmac_md5 = hmac.new(password)
        hmac_md5.update(chal)

        # base64 encoding
        msg = BareosBase64().string_to_base64(bytearray(hmac_md5.digest()))

        # send the base64 encoding to director
        self.send(msg)
        received = self.recv()
        if  ProtocolMessages.is_auth_ok(received):
            result = True
        else:
            self.logger.error("failed: " + received)
        return (ssl, compatible, result)


    def __set_status(self, status):
        self.status = status
        status_text = Constants.get_description(status)
        self.logger.debug(str(status_text) + " (" + str(status) + ")")


    def _set_state_director_prompt(self):
        self.send(".")
        msg = self.recv_msg()
        self.logger.debug("received message: " + msg)
        # TODO: check prompt
        return True


    def _handleSocketError(self, exception):
        self.logger.error("socket error:" + str(exception))
        self.socket = None