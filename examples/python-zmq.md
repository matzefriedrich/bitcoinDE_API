## Connect to ZeroMQ PUB socket using Python and zmq

````python
import zmq
import msgpack
import threading

self.context = zmq.Context()

def create_pull_socket(port: int):
    self.default_consumer = self.context.socket(zmq.SUB)
    address = "tcp://127.0.0.1:%s" % port
    self.default_consumer.connect(address)
    any_topic = b""
    # an empty string will make the client receive all messages regardless of what the string prefix is
    self.default_consumer.setsockopt(zmq.SUBSCRIBE, any_topic)

    self.consumer_poller = zmq.Poller()
    self.consumer_poller.register(self.default_consumer, zmq.POLLIN)

    continue_poll = True
    while continue_poll:
        events = dict(self.consumer_poller.poll())
        if self.default_consumer in events and events[self.default_consumer] == zmq.POLLIN:
            message = self.default_consumer.recv()
            evt = msgpack.unpackb(message)

threading.Thread(target=create_pull_socket, (5634), ).start()
````