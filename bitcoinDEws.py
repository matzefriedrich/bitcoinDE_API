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
from hashlib import sha1
from json import loads

from os import urandom
from base64 import b64encode  # Websocket Key handling
from struct import unpack  # Websocket Length handling

from twisted.internet import endpoints, reactor, task  # unfortunately reactor is needed in ClientIo0916Protocol
from twisted.internet.ssl import optionsForClientTLS
from twisted.internet.protocol import Factory
from twisted.application.internet import ClientService
from twisted.protocols import basic


class ClientIo0916Protocol(basic.LineReceiver):
    """Implements a receiver able to interact with the websocket part of a JS clientIO server.
Requests options from the clientIO server and if websocket is available, upgrades the connection 'talk' websocket.
After acting as a basic.LineReceiver to process the http GET,UPGRADE part (lineReceived), switch to RAW
mode (rawDataReceived)."""
    _MAGIC = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"  # Handshake key signing

    def connectionMade(self):
        """ Called after the factory that was passed this protocol established the connection. """
        self.state = 0  # pseudo state-machine to keep track which phase http-upgrade-websocket the connection is in
        self.http_pos = ""
        self.http_length = 0

        self.pong_count = 0
        self.ping_count = 0
        self.last_ping_at = 0
        self.ping_interval = 0

        self.setLineMode()  # for the http part, process the packet line-wise
        data = "GET /socket.io/1/?t=%d HTTP/1.1\n" % (time() * 1000)
        self.sendLine(data.encode('utf8'))  # first GET request

    def heart_beat(self):
        self.pong_count += 1
        pong = bytearray([129, 3]) + b"2::"
        # pong = bytearray([1,3])+bytes("2::") # Produces more reconnects
        self.transport.write(bytes(pong))

    def parse_http(self, line):
        """Processes the response to the GET Request and create the UPGRADE Request"""
        nonce, t1, t2, options = line.split(":")
        if "websocket" in options:
            if len(nonce) == 20:
                key = b64encode(urandom(16))
                self.websocket_key = key.decode('utf8')
                data = "GET /socket.io/1/websocket/%s HTTP/1.1\r\n" % nonce
                # data += "Accept-Encoding: gzip, deflate, sdch"
                data += "Connection: Upgrade\r\nUpgrade: websocket\r\n"
                data += "Sec-WebSocket-Key: %s\r\n" % self.websocket_key
                data += "Sec-WebSocket-Version: 13\r\n"
                data += "Sec-WebSocket-Extensions: \r\n"
                # data += "Sec-WebSocket-Extensions: permessage-deflate\r\n";
                data += "Pragma: no-cache\r\nCache-Control: no-cache\r\n"
                self.sendLine(data.encode('utf8'))
                self.state = 1

    def eat_up_http(self, line):
        if self.http_pos == "head":
            if line == "":
                self.http_pos = "length"
        elif self.http_pos == "length":
            self.http_length = int(line)
            self.http_pos = "content"
        elif self.http_pos == "content":
            if line != "":
                self.parse_http(line)
                self.http_length -= len(line)
                if self.http_length <= 0:
                    self.http_pos = "tail"
            else:
                self.http_pos = "tail"
        elif self.http_pos == "tail":
            if line == "":
                self.http_pos = ""

    def rawDataReceived(self, data):
        t = time()
        if type(data) == str:
            data = bytearray(data)
        if self.state == 2:
            self.state = 3
        elif self.state == 3:
            # Calculate the length
            length, b = data[1] & 0b1111111, 2  # Handle the length field

            if length == 126:
                b = 4
                length = unpack('!H', data[2:4])[0]  # struct.unpack
            elif length == 127:
                b = 10
                length = unpack('!Q', data[2:10])[0]
            # Different Opcodes

            if data[b] == 47:
                print(data)
            elif data[b] == 48:
                self.ping_count += 1
                self.process_ping(data[b:])

            elif data[b] == 53:
                self.on_packet_received(data[b:].decode("utf8"), length - b, t)
            else:
                print("Unknown op-code", data)
            reactor.callLater(25, self.heart_beat)
        else:
            print("Unknown state", self.state)

    def process_ping(self, data):
        now = time()
        if self.last_ping_at != 0:
            since = now - self.last_ping_at
            self.ping_interval = since
        self.last_ping_at = now
    # print "---> ping",self.ping_count,"%0.2f"%since,"\t",data

    def lineReceived(self, line):
        """Parse the http Packet (line-wise) and switch states accordingly"""
        line = line.decode('utf8')
        if "HTTP/1.1" in line:  # First line in response
            lc = line.split(" ")
            http, code, phrase = lc[0], int(lc[1]), " ".join(lc[2:])
            if code == 200:
                self.http_pos = "head"
            elif code == 101:
                self.state = 1
            else:
                self.http_pos = ""
                self.terminate([code, phrase])
        elif self.state == 0:
            self.eat_up_http(line)
        elif self.state == 1:
            if "Sec-WebSocket-Accept:" in line:
                key_got = line.split(" ")[1]
                hash_algorithm = sha1()
                hash_algorithm.update(self.websocket_key.encode('utf8') + self._MAGIC)
                key_accept = b64encode(hash_algorithm.digest()).decode('utf8')
                if key_got == key_accept:
                    print("WS 0.9 connection accepted")
                    self.state = 2
                else:
                    self.terminate(["key mismatch", key_got, key_accept])
            elif "Upgrade:" in line:
                if line.split(" ")[1] != "websocket":
                    self.terminate(["Upgrade to websocket failed", line])
        elif self.state == 2:
            if line == "":  # Wait for the packet to end
                self.setRawMode()
            else:
                print("Should never happen", len(line), line)
        else:
            print("unexpected:", line)

    #
    def terminate(self, reason):
        print("ClientIo0916Protocol.terminate", reason)

    def on_packet_received(self, data, length, t):
        """ Dummy, implement Your own websocket-packet-processing"""
        print("ClientIo0916Protocol.on_packet_received", length, data)

    def connectionLost(self, reason):
        print("ClientIo0916Protocol.connectionLost", reason)


class WebSocketJsonBitcoinDEProtocol(ClientIo0916Protocol):
    """ Processes the Content of the Websocket packet treating it as JSON and pass the dict to an onEvent-function
    mimicking the original js behaviour"""

    def on_packet_received(self, data, length, t):
        i = 1
        while data[i] == ":":
            i += 1
        json_data = loads(data[i:])  # json.loads
        evt, args = json_data["name"], json_data["args"][0]
        self.factory.on_event(evt, args, t)

    def terminate(self, reason):
        print("WebSocketJsonBitcoinDEProtocol.terminate(%s)", reason)

    def connectionLost(self, reason):
        print("WebSocketJsonBitcoinDEProtocol.connectionLost", reason)


# * * * * * * * * * * * socket.io > 2.0 Implementation * * * * * * * * * * * #

class ClientIo2011Protocol(basic.LineReceiver):
    _MAGIC = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"  # Handshake key signing

    def connectionMade(self):
        self.nonce = time() * 1000
        self.header = [{"lines": []}]
        self.eio = 3

        self.pingInterval = 20
        self.ping_count = 0
        self.next_len = 0

        self.setLineMode()
        self.send_init()

    def send_init(self):
        cookie = self.header[-1].get("cookie", "")
        if len(cookie) > 0:
            cookie = "&io=" + cookie
        data = "GET /socket.io/1/?EIO=%d%s&t=%d-0&transport=polling HTTP/1.1\r\n" % (self.eio, cookie, self.nonce)
        self.sendLine(data.encode('utf8'))  # first GET request

    def lineReceived(self, line):
        if len(line) > 3:
            self.header[-1]["lines"].append(line)
        else:
            self.on_http_header()

    def on_http_header(self):
        upgrade = False
        header = self.header[-1]
        code = ""
        for line in header["lines"]:
            line = line.decode('utf8')
            if "HTTP/1.1" in line:
                words = line.split("HTTP/1.1 ")[1].split(" ")
                code, word = words[0], " ".join(words[1:])
                header["code"] = code
            if "Set-Cookie:" in line:
                cookie = line.split("=")[1].split(";")[0]
                header["cookie"] = cookie
            elif '"upgrades"' in line:
                upgrade = True
            elif "Upgrade:" in line:
                header["Upgrade"] = line.split(": ")[-1]
            elif "Sec-WebSocket-Accept" in line:
                header["Key"] = line.split(": ")[-1]

            if "pingInterval" in line:  # Retrieve pingInterval from Response
                inter = line.split("pingInterval")
                if len(inter) > 1:
                    self.pingInterval = int(inter[1].split(":")[1].split(",")[0]) / 1100

        if code == "200":
            if not upgrade:
                self.send_init()
            else:
                self.send_upgrade()
        elif code == "101":
            self.check_websocket()
        else:
            print(code, header)

        self.header.append({"lines": []})

    def send_upgrade(self):
        key = b64encode(urandom(16))
        self.websocket_key = key
        data = "GET /socket.io/1/?EIO=%d&transport=websocket&t=%d-2%s HTTP/1.1\r\n" % (
            self.eio, time() * 1000, self.header[-1].get("cookie", ""))
        data += "Connection: Upgrade\r\nUpgrade: Websocket\r\n"
        data += "Sec-WebSocket-Key: %s\r\n" % (self.websocket_key.decode('utf8'))
        data += "Sec-WebSocket-Version: 13\r\n"
        data += "Pragma: no-cache\r\nCache-Control: no-cache\r\n"
        self.sendLine(data.encode('utf8'))

    def check_websocket(self):
        key_got = self.header[-1].get("Key", "")
        hash_algorithm = sha1()
        hash_algorithm.update(self.websocket_key + self._MAGIC)
        key_accept = b64encode(hash_algorithm.digest()).decode('utf8')
        if key_got == key_accept:
            self.setRawMode()
            reactor.callLater(3, self.send_ping)
            reactor.callLater(2, self.request_market)
            print("WS 2.0 connection accepted")

    def rawDataReceived(self, data):
        if type(data) == str:
            data = bytearray(data)

        t = time()
        if len(data) > 4:
            # print self.next_len,map(ord,data[:8]),data[:20],data[-20:]
            sd = data.split("42/market,".encode('utf8'))
            if len(sd) >= 2:
                # len(data),self.next_len	# socket.io does weird things with it's length==4 packets...
                content = (sd[1]).decode('utf8')
                self.on_packet_received(content, len(content), t)

                self.next_len = 0
        elif len(data) == 4:
            self.next_len = unpack('!H', data[2:4])[0]
        elif len(data) == 3:
            if data[1] == 1 and data[2] == 51:
                reactor.callLater(self.pingInterval, self.send_ping)
                self.next_len = 0
            else:
                self.next_len = 0
                print("short unknown")
        else:
            self.next_len = 0
            print("Unknown", data)

    def send_ping(self):
        self.ping_count += 1
        # print "Send Ping"
        ping = bytearray([129, 1]) + bytes("2".encode('utf8'))
        self.transport.write(bytes(ping))

    def request_market(self):
        sd = b"40/market,"
        # print "Send RequestMarket"
        sp = bytearray([129, len(sd)]) + bytes(sd)
        self.transport.write(bytes(sp))

    def terminate(self, reason):
        print("Terminate", reason)

    def on_packet_received(self, data, length, t):
        """ Dummy, implement Your own websocket-packet-processing"""
        print("Packet", length, data)

    def connectionLost(self, reason):
        print("connectionLost", reason)


class WebSocketJsonBitcoinDEProtocol2(ClientIo2011Protocol):
    """ Processes the Content of the Websocket packet treating it as JSON and pass the dict to an onEvent-function
    mimicking the original js behaviour"""

    def on_packet_received(self, data, length, t):
        di = data.index(',')
        evt, args = data[2:di - 1], loads(data[di + 1:-1])
        self.factory.on_event(evt, args, t)

    def terminate(self, reason):
        print("WebSocketJsonBitcoinDEProtocol2.terminate", reason)

    def connectionLost(self, reason):
        print("WebSocketJsonBitcoinDEProtocol2.connectionLost", reason)


# * * * * * * * * * * * MultiSource Factories * * * * * * * * * * * #

class MultiSource(Factory):

    def __init__(self, sid, receiver):
        self.sid = sid
        self.receiver = receiver

    def __str__(self):
        return "WSSource%d %s" % (self.sid, self.WSversion)

    def on_event(self, evt, data, t):
        self.receiver.receive_event(evt, data, self.sid, t)


class BitcoinWSSourceV09(MultiSource):
    protocol = WebSocketJsonBitcoinDEProtocol
    WebSocketApiVersion = "09"

    def __str__(self):
        return "WSSource%d %s" % (self.sid, self.WebSocketApiVersion)

    def startFactory(self):
        print("%s started" % self)

    def started_connecting(self, connector):
        print("%s connected %d" % (self, connector))

    def lost(self):
        print("\t%s client called lost" % self)

    def connection_lost(self, connector, reason):
        print("\t%s connection_lost" % self, connector, reason)


class BitcoinWSSourceV20(BitcoinWSSourceV09):
    protocol = WebSocketJsonBitcoinDEProtocol2
    WebSocketApiVersion = "20"


# * * * * * * * * * * MultiSource Implementation * * * * * * * * * * #

class Event(object):
    def __init__(self, event_id, event_type):
        self.eventID = event_id
        self.eventType = event_type

        self.sources = []
        self.eventData = {}

    def add_source(self, at, src):
        self.sources.append((at, src,))

    def add_data(self, data):
        self.eventData = data

    def since(self):
        if len(self.sources) == 0:
            return 0, 0, ""
        else:
            self.sources = sorted(self.sources, key=lambda x: x[0])
            srcs = [x[1] for x in self.sources]
            return self.sources[0][0], self.sources[-1][0] - self.sources[0][0], srcs

    def __str__(self):
        return "Event %s %s %s" % (self.eventType, self.eventID, self.eventData)


class BitcoinWebSocketEventStream(object):
    """Handles an event stream, for example 'add'-Events. ProcessEvent only forwards the first occurrence of an event
    from one of the sources. Already received events get timestamped-data via AddSource"""

    def __init__(self, stream, interval=60):
        self.stream = stream
        self.checktask = task.LoopingCall(self.clean_up)
        self.interval = interval  # Remove old Events from stream
        self.checktask.start(self.interval, False)
        self.events = {}

    def clean_up(self):
        """Periodically removes old events from stream"""
        now = time()
        events = {}
        n, m, dt, ll, srcl = 0, 0, [1000, 0, 0], {}, {}
        for k, v in self.events.items():
            s, d, srcs = v.since()
            if s >= now - self.interval:
                events[k] = v
                n += 1
            else:
                m += 1
                dt[0] = min(dt[0], d)
                dt[1] += d
                dt[2] = max(dt[2], d)

                src, length = srcs[0], len(srcs)
                srcl[src] = srcl.get(src, 0) + 1
                ll[length] = ll.get(length, 0) + 1

        if m > 0:
            dt[1] = dt[1] / (1. * m)
        else:
            dt[0] = 0

        self.events = events
        print("Cleanup", self.stream, n, m, map(lambda x: "%.6f" % x, dt), ll, srcl)

    def process_event(self, data, src, t):
        event_id = self.GenerateID(data)

        is_new = False
        evt = self.events.get(event_id, None)
        if evt is None:
            evt = Event(event_id, self.stream)
            evt.add_data(self.retrieve_data(data))
            self.events[event_id] = evt
            is_new = True
        evt.add_source(t, src)

        if is_new:
            return evt
        else:
            return None

    def retrieve_data(self, data):
        return data


class BitcoinWebSocketRemoveOrder(BitcoinWebSocketEventStream):
    def __init__(self):
        super(BitcoinWebSocketRemoveOrder, self).__init__("rm")

    @staticmethod
    def generate_id(data):
        return data['id']


class Countries(object):
    def __init__(self):
        self.codes = ["DE", "AT", "CH", "BE", "GR", "MT", "SI", "BG", "IE", "NL", "SK", "DK", "IT", "ES", "HR", "PL",
                      "CZ", "EE", "LV", "PT", "HU", "FI", "LT", "RO", "GB", "FR", "LU", "SE", "CY", "IS", "LI", "NO",
                      "MQ"]

    def decode(self, u):
        pass

    @staticmethod
    def encode(codes):
        i, j = 0, 0


class BitcoinWebSocketAddOrder(BitcoinWebSocketEventStream):
    def __init__(self):
        super(BitcoinWebSocketAddOrder, self).__init__("add")

        self.countries = Countries()

        self.trans = {"uid": ("uid", lambda x: x),
                      "order_id": ("oid", lambda x: x),
                      "id": ("DEid", lambda x: int(x)),
                      "price": ("price", lambda x: int(float(x) * 100)),
                      "trading_pair": ("pair", lambda x: x),
                      "bic_full": ("cBIC", lambda x: x),
                      "only_kyc_full": ("rkyc", lambda x: int(x)),
                      "is_kyc_full": ("ukyc", lambda x: int(x)),
                      "amount": ("amt", lambda x: float(x)),
                      "min_amount": ("mamt", lambda x: float(x)),
                      "order_type": ("type", lambda x: x),
                      "order": ("order", lambda x: x),
                      "min_trust_level": ("trust", lambda x: {"bronze": 1,
                                                              "silver": 2,
                                                              "gold": 3,
                                                              "platinum": 4}.get(x, 0),),
                      "seat_of_bank_of_creator": ("seat", lambda x: x),
                      "trade_to_sepa_country": ("country", lambda x: x),
                      "fidor_account": ("fidor", lambda x: int(x))}
        # self.trans["is_shorting"]
        # self.trans["is_shorting_allowed"]

    @staticmethod
    def generate_id(data):
        return data['id']

    def retrieve_data(self, data):
        short = int(data["is_shorting"]) * 2 + int(data["is_shorting_allowed"])

        fidor = int(data["is_trade_by_fidor_reservation_allowed"])
        sepa = int(data["is_trade_by_sepa_allowed"])
        po = int(data["payment_option"])
        r = {"po": po, "short": short}

        print(fidor, sepa, po, short)
        for k, v in self.trans.items():
            t, f, = v
            r[t] = f(data.get(k))

        return r


class BitcoinWebSocketSkn(BitcoinWebSocketEventStream):
    def __init__(self):
        super(BitcoinWebSocketSkn, self).__init__("skn")

    @staticmethod
    def generate_id(data):
        return data['uid']


class BitcoinWebSocketSpr(BitcoinWebSocketEventStream):
    def __init__(self):
        super(BitcoinWebSocketSpr, self).__init__("spr")

    @staticmethod
    def generate_id(data):
        return data['uid']


class BitcoinWebSocketRpo(BitcoinWebSocketEventStream):
    def __init__(self):
        super(BitcoinWebSocketRpo, self).__init__("po")

    @staticmethod
    def generate_id(data):
        h, j = 0, 1
        for k, v in data.items():
            m = (int(v.get("is_trade_by_fidor_reservation_allowed", "0")) * 2 - 1)
            h += int(k) * m * j
            j += 1
        return h

    def retrieve_data(self, data):
        pos = {}
        for k, v in data.items():
            fidor = int(v.get("is_trade_by_fidor_reservation_allowed", "0"))
            sepa = int(v.get("u'is_trade_by_sepa_allowed", "0"))
            po = fidor + sepa * 2
            pos[int(k)] = po
        return pos


class BitcoinWebSocketMulti(object):
    """ClientService ensures restart after connection is lost."""

    def __init__(self, servers=[1, 2, 3, 4]):
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
