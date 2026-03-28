import threading
import time


class SubscriptionIndex:
    def __init__(self):
        self.listeners_by_topic = {}

    def refresh_and_snapshot(self, events):
        workers = []
        for event in events:
            worker = threading.Thread(target=self._apply_event, args=(event,))
            worker.start()
            workers.append(worker)

        snapshot = self._snapshot_topics()

        for worker in workers:
            worker.join()

        return snapshot

    def _apply_event(self, event):
        listeners = self.listeners_by_topic.setdefault(event["topic"], {})
        time.sleep(0.001)

        if event["action"] == "subscribe":
            listeners[event["listener_id"]] = {"region": event["region"]}
        else:
            listeners.pop(event["listener_id"], None)
            if not listeners:
                self.listeners_by_topic.pop(event["topic"], None)

    def _snapshot_topics(self):
        snapshot = {}
        for topic, listeners in self.listeners_by_topic.items():
            time.sleep(0.001)
            snapshot[topic] = len(listeners)
        return snapshot