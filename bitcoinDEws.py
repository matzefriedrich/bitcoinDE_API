#!/usr/bin/env python3.7
# coding:utf-8

###############################################################################
#
# The MIT License (MIT)
#
# Copyright (c) 2016 Matthias Linden
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NON-INFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
############################################################################### 

from time import time


from twisted.internet import endpoints, reactor  # unfortunately reactor is needed in ClientIo0916Protocol
from twisted.internet.ssl import optionsForClientTLS
from twisted.application.internet import ClientService

from bitcoinde.eventhandlers import \
    BitcoinWebSocketAddOrder, \
    BitcoinWebSocketRemoveOrder, \
    BitcoinWebSocketRpo, \
    BitcoinWebSocketSkn, \
    BitcoinWebSocketSpr

from bitcoinde.factories import BitcoinWSSourceV09, BitcoinWSSourceV20


class BitcoinWebSocketMulti(object):
    """ClientService ensures restart after connection is lost."""

    def __init__(self, servers=[1, 3, 4]):
        self.servers = {1: ("ws", BitcoinWSSourceV09,),
                        2: ("ws1", BitcoinWSSourceV09,),
                        3: ("ws2", BitcoinWSSourceV20,),
                        4: ("ws3", BitcoinWSSourceV20,)}

        self.sources = {}

        self.connService = {}

        self.streams = {"remove_order": BitcoinWebSocketRemoveOrder(),
                        "add_order": BitcoinWebSocketAddOrder(),
                        "skn": BitcoinWebSocketSkn(),
                        "spr": BitcoinWebSocketSpr(),
                        "refresh_express_option": BitcoinWebSocketRpo()}

        for sid in servers:
            addr, factory_creator, = self.servers.get(sid, (None, None,))
            if addr is not None:
                context_factory = optionsForClientTLS(u'%s.bitcoin.de' % addr, None)
                endpoint = endpoints.SSL4ClientEndpoint(reactor, '%s.bitcoin.de' % addr, 443, context_factory)
                factory = factory_creator(sid, self)
                self.sources[sid] = factory  # Reference to self is passed here, ReceiveEvent is called by source
                client_service = ClientService(endpoint, factory)
                self.connService[sid] = client_service
                client_service.startService()

    def receive_event(self, evt, data, src, t):
        # Called by source, dispatches to event stream
        t2 = time()
        stream = self.streams.get(evt, None)
        evt = None
        if stream is not None:
            evt = stream.process_event(data, src, t)
        else:
            print("no Event stream for", src, evt, data, t2 - t)

        if evt is not None:
            self.deliver(evt)

    def deliver(self, evt):
        print(evt)

    def stats(self):
        pass


class BitcoinDESubscribe(BitcoinWebSocketMulti):
    funcs = {"add": [], "rm": [], "po": [], "skn": [], "spr": []}

    def deliver(self, evt):
        tpy = evt.eventType
        for f in self.funcs[tpy]:
            f(evt)

    def subscribe_add(self, func):
        self.funcs["add"].append(func)

    def subscribe_remove(self, func):
        self.funcs["rm"].append(func)

    def subscribe_management(self, func):
        self.funcs["skn"].append(func)
        self.funcs["spr"].append(func)

    def subscribe_update(self, func):
        self.funcs["po"].append(func)


# * * * * * * * * * * * * * * main * * * * * * * * * * * * * * #

def main():
    sources = BitcoinWebSocketMulti()

    reactor.run()


if __name__ == '__main__':
    main()
