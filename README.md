# Bitcoin.de WebSocket client (socket.io)

Code artifacts included with this repository have been forked from the https://github.com/matthiaslinden/bitcoinDE_API 
repository. The API has been tested against Python 3.7 (especially a remote Python configuration using Docker). See the original
repository for further details about implemented API client functionality.

## Changes

* added Docker support
* fixed code issues (code has been aligned with PEP-8)
* fixed typos, and also removed informational comments
* adjusted OOP-design (made changes to inheritance)
  add event-sinks objects 
* disabled ws1-endpoint, since this one does not seem to work without issues
* removed imprecise/noisy debug outputs
* adds support for event sinks to `MultiSource`
* adds a ZeroMQ PUB socket event sink (publishes message-packed events)

## ZeroMQ PUB socket

The application opens a ZeroMQ PUB socket server on port `5634` that does not use any topics. Any event aggregated by
the `MultiSource` client gets published over the socket. Event data is encoded/packed using `msgpack` (see `pack` 
method in `Event` class). The message has the following format:

````python
message = {
    "type": self.event_type, 
    "id": self.event_id,
    "data": self.event_data
}
````
