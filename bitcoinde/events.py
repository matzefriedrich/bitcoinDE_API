# from time import time
# from twisted.internet import task


class Event(object):
    def __init__(self, event_id, event_type):
        self.event_id = event_id
        self.event_type = event_type

        self.sources = []
        self.event_data = {}

    def add_source(self, at, src):
        self.sources.append((at, src,))

    def add_data(self, data):
        self.event_data = data

    def since(self):
        if len(self.sources) == 0:
            return 0, 0, ""
        else:
            self.sources = sorted(self.sources, key=lambda x: x[0])
            sources = [x[1] for x in self.sources]
            return self.sources[0][0], self.sources[-1][0] - self.sources[0][0], sources

    def __str__(self):
        return "Event %s %s %s" % (self.event_type, self.event_id, self.event_data)


class BitcoinWebSocketEventHandler(object):
    """Handles an event stream, for example 'add'-Events. ProcessEvent only forwards the first occurrence of an event
    from one of the sources. Already received events get timestamped-data via AddSource"""

    def __init__(self, event_name: str, interval=60):
        self.event_name = event_name
        from twisted.internet import task
        self.check_task = task.LoopingCall(self.__clean_up)
        self.interval = interval  # Remove old Events from stream
        self.check_task.start(self.interval, False)
        self.events = {}

    """Must be implemented by derived types."""
    def generate_id(self, data) -> str:
        return None

    def __clean_up(self):
        """Removes old events from stream periodically (automatically called by reactor using a LoopingCall)."""
        from time import time
        now = time()
        events = {}
        n, m, dt, ll, srcl = 0, 0, [1000, 0, 0], {}, {}
        for key, value in self.events.items():
            s, d, sources = value.since()
            if s >= now - self.interval:
                events[key] = value
                n += 1
            else:
                m += 1
                dt[0] = min(dt[0], d)
                dt[1] += d
                dt[2] = max(dt[2], d)

                src, length = sources[0], len(sources)
                srcl[src] = srcl.get(src, 0) + 1
                ll[length] = ll.get(length, 0) + 1

        if m > 0:
            dt[1] = dt[1] / (1. * m)
        else:
            dt[0] = 0

        self.events = events
        print("Cleanup", self.event_name, n, m, map(lambda x: "%.6f" % x, dt), ll, srcl)

    def process_event(self, data, src, t) -> Event:
        event_id = self.generate_id(data)

        evt = self.events.get(event_id, None)  # check whether the event has been seen before
        try:
            if evt is None:  # should be None, if the event is a new one
                evt = Event(event_id, self.event_name)
                event_data = self.retrieve_data(data)
                evt.add_data(event_data)
                self.events[event_id] = evt
                return evt
        finally:
            evt.add_source(t, src)

        return None

    def retrieve_data(self, data):
        return data
