from time import time
from hashlib import sha1
from json import loads
from os import urandom
from base64 import b64encode  # Websocket Key handling
from struct import unpack  # Websocket Length handling
from twisted.protocols import basic
from twisted.internet import reactor


class ClientIo0916Protocol(basic.LineReceiver):
    """Implements a receiver able to interact with the websocket part of a JS clientIO server.
Requests options from the clientIO server and if websocket is available, upgrades the connection 'talk' websocket.
After acting as a basic.LineReceiver to process the http GET,UPGRADE part (lineReceived), switch to RAW
mode (rawDataReceived)."""
    _MAGIC = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"  # Handshake key signing

    def __init__(self):
        self.state = 0
        # pseudo state-machine to keep track which phase http-upgrade-websocket the connection is in
        self.http_pos = ""
        self.http_length = 0

        self.pong_count = 0
        self.ping_count = 0
        self.last_ping_at = 0
        self.ping_interval = 0

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
        """Parse the http packet (line-wise) and switch states accordingly"""
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

    def terminate(self, reason):
        print("ClientIo0916Protocol.terminate", reason)

    def on_packet_received(self, data, length, t):
        """Must be implemented by a derived type."""
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
        event_type, args = json_data["name"], json_data["args"][0]
        self.factory.on_event(event_type, args, t)

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