#!/usr/bin/env python3.7
# coding:utf-8
from __future__ import annotations  # enable code compatibility
from time import time

import zmq

from twisted.internet import endpoints, reactor  # unfortunately reactor is needed in ClientIo0916Protocol
from twisted.internet.ssl import optionsForClientTLS
from twisted.application.internet import ClientService

from bitcoinde.eventhandlers import \
    BitcoinWebSocketAddOrder, \
    BitcoinWebSocketRemoveOrder, \
    BitcoinWebSocketRpo, \
    BitcoinWebSocketSkn, \
    BitcoinWebSocketSpr

from bitcoinde.events import Event, BitcoinWebSocketEventHandler, EventSink
from bitcoinde.factories import BitcoinWSSourceV09, BitcoinWSSourceV20


class BitcoinWebSocketMulti(object):
    """ClientService ensures restart after connection is lost."""

    def __init__(self, servers=[1, 3, 4]):
        self.sinks = []  # a list of event sinks
        self.servers = {1: ("ws", BitcoinWSSourceV09,),
                        2: ("ws1", BitcoinWSSourceV09,),
                        3: ("ws2", BitcoinWSSourceV20,),
                        4: ("ws3", BitcoinWSSourceV20,)}

        self.sources = {}

        self.connService = {}  # a backing field used to store client-services

        self.event_handlers = {"remove_order": BitcoinWebSocketRemoveOrder(),
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

    def get_event_handler(self, event_type: str) -> BitcoinWebSocketEventHandler:
        """Finds a handler for the specified type of event."""
        return self.event_handlers.get(event_type, None)

    def receive_event(self, event_type: str, data: dict, src: int, unix_time_seconds: float):
        """Dispatches received events. Finds handler for given event. This method will be called by an
        event-source component."""
        current_unix_time_seconds: float = time()
        event_handler: BitcoinWebSocketEventHandler = self.get_event_handler(event_type)
        event: Event = None
        if event_handler is not None:
            event = event_handler.process_event(data, src, unix_time_seconds)
        else:
            print("no Event stream for", src, event_type, data, current_unix_time_seconds - unix_time_seconds)

        if event is not None:
            self.deliver(event)

    def write_to(self, sink: EventSink) -> BitcoinWebSocketMulti:
        """Registers the given event sink with the current multi-source instance."""
        self.sinks.append(sink)
        return self

    def deliver(self, event: Event):
        """Pushes the given event to all registered sinks."""
        for sink in self.sinks:  # type: EventSink
            sink.process_event(event)

    def stats(self):
        pass


class ZeroMqEventProcessingSink(EventSink):

    def __init__(self, port: int):
        """Initializes a PUSH socket using the given port."""
        self.port = port

        self.context = zmq.Context()

        def create_default_pull_socket():
            self.default_consumer = self.context.socket(zmq.SUB)
            address = "tcp://127.0.0.1:%s" % port
            print('Connecting pull-socket to address %s' % address)
            self.default_consumer.connect(address)
            any_topic = b""
            # an empty string will make the client receive all messages regardless of what the string prefix is
            self.default_consumer.setsockopt(zmq.SUBSCRIBE, any_topic)

            self.consumer_poller = zmq.Poller()
            self.consumer_poller.register(self.default_consumer, zmq.POLLIN)
            print("Started default push socket consumer on port: %s" % port)
            continue_poll = True
            while continue_poll:
                events = dict(self.consumer_poller.poll())
                if self.default_consumer in events and events[self.default_consumer] == zmq.POLLIN:
                    message = self.default_consumer.recv()
                    if message == "exit":
                        continue_poll = False
                    else:
                        print("Sub socket received data: %s" % message)

        def create_pub_socket():
            self.socket = self.context.socket(zmq.PUB)
            address = 'tcp://*:%s' % port
            print('Binding pub-socket to address %s' % address)
            self.socket.bind(address)
            print("Running server on port: %s" % port)

        import threading
        threading.Thread(target=create_default_pull_socket).start()
        threading.Thread(target=create_pub_socket).start()

    def process_event(self, event: Event):
        """Sends the given event to a PUSH socket."""
        packed = event.pack()
        self.socket.send(packed, )


def main():
    sources = BitcoinWebSocketMulti()
    sources.write_to(ZeroMqEventProcessingSink(5634))

    reactor.run()


if __name__ == '__main__':
    main()
