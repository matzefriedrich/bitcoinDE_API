#!/usr/bin/env python3.7
# coding:utf-8

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

        self.connService = {}  # a backing field used to store client-services

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
                self.sources[sid] = factory  # Reference to self is passed here, receive_event is called by source
                client_service = ClientService(endpoint, factory)
                self.connService[sid] = client_service
                client_service.startService()

    def receive_event(self, evt, data, src, t):
        """Dispatches received events. Finds handler for given event. This method will be called by an
        event-source component."""
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
        """Obsolete."""
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
