"""
Reimplementation of the bconsole program in python.
"""

from   bareos.bsock.bsock import BSock
from   pprint import pformat, pprint
import json

class BSockJson(BSock):
    """
    use to send and receive the response from director
    """

    def __init__(self,
                 address="localhost",
                 port=9101,
                 dirname=None,
                 name="*UserAgent*",
                 password=None):
        super(BSockJson, self).__init__(
            address, port, dirname, name,
            password)


    def call(self, command):
        json = self.call_fullresult(command)
        if json == None:
            return
        if json.has_key('result'):
            result = json['result']
        else:
            # TODO: or raise an exception?
            result = json
        return result


    def call_fullresult(self, command):
        resultstring = super(BSockJson, self).call(command)
        data = None
        if resultstring:
            try:
                data = json.loads(resultstring)
            except ValueError as e:
                # in case result is not valid json,
                # create a JSON-RPC wrapper
                data = {
                    'error': {
                        'code': 2,
                        'message': str(e),
                        'data': resultstring
                    },
                }
        return data


    def interactive(self):
        """
        Enter the interactive mode.
        """
        self._set_state_director_prompt()
        command = ""
        while command != "exit" and command != "quit":
            command = raw_input(">>")
            if command:
                pprint(self.call(command))
        return True


    def _set_state_director_prompt(self):
        result = False
        if super(BSockJson, self)._set_state_director_prompt():
            # older version did not support compact mode,
            # therfore first set api mode to json (which should always work in bareos >= 15.2.0)
            # and then set api mode json compact (which should work with bareos >= 15.2.2)
            self.call(".api json")
            self.call(".api json compact=yes")
            result = True
        return result
