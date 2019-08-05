from twisted.internet.protocol import Factory

from bitcoinde.protocol import WebSocketJsonBitcoinDEProtocol2, WebSocketJsonBitcoinDEProtocol


class MultiSource(Factory):

    def __init__(self, sid, receiver):
        """Special ctor; signature cannot be changed."""
        self.sid = sid
        self.receiver = receiver
        self.socket_version = None

    def __str__(self):
        return "MultiSource%d %s" % (self.sid, self.socket_version)

    def on_event(self, event_type: str, data, t):
        self.receiver.receive_event(event_type, data, self.sid, t)

    def startFactory(self):
        print("%s started" % self)

    def started_connecting(self, connector):
        print("%s connected %d" % (self, connector))

    def lost(self):
        print("\t%s client called lost" % self)

    def connection_lost(self, connector, reason):
        print("\t%s connection_lost" % self, connector, reason)


class BitcoinWSSourceV09(MultiSource):
    protocol = WebSocketJsonBitcoinDEProtocol

    def __init__(self, sid, receiver):
        """Special ctor; signature cannot be changed."""
        super(BitcoinWSSourceV09, self).__init__(sid, receiver)
        self.socket_version = "09"

    def __str__(self):
        return "MultiSource%d %s" % (self.sid, self.socket_version)


class BitcoinWSSourceV20(BitcoinWSSourceV09):
    protocol = WebSocketJsonBitcoinDEProtocol2

    def __init__(self, sid, receiver):
        """Special ctor; signature cannot be changed."""
        super(BitcoinWSSourceV20, self).__init__(sid, receiver)
        self.socket_version = "20"

    def __str__(self):
        return "MultiSource%d %s" % (self.sid, self.socket_version)