"""
Communicates with the bareos-director
"""

from   bareos.bsock.lowlevel import LowLevel
from   bareos.exceptions import *
import sys

class BSock(LowLevel):
    '''use to send and receive the response from director'''

    def __init__(self,
                 address="localhost",
                 port=9101,
                 dirname=None,
                 name="*UserAgent*",
                 password=None):
        super(BSock, self).__init__()
        self.connect(address, port, dirname)
        self.auth(name=name, password=password)
        self._set_state_director_prompt()


    def call(self, command):
        '''
        call a bareos-director user agent command
        '''
        return self.__call(command, 0)

    def __call(self, command, count):
        '''
        Call a bareos-director user agent command.
        If connection is lost, try to reconnect.
        '''
        result = ''
        try:
            self.send(str(command))
            result = self.recv_msg()
        except (SocketEmptyHeader, ConnectionLostError) as e:
            self.logger.error("connection problem (%s): %s" % (type(e).__name__, str(e)))
            if count == 0:
                if self.reconnect():
                    return self.__call(command, count+1)
        return result

    def send_command(self, commamd):
        return self.call(command)


    def interactive(self):
        """
        Enter the interactive mode.
        Exit via typing "exit" or "quit".
        """
        self._set_state_director_prompt()
        command = ""
        while command != "exit" and command != "quit":
            command = raw_input(">>")
            resultmsg = self.call(command)
            sys.stdout.write(resultmsg)
        return True
