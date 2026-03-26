import threading
import time


class NotificationDispatcher:
    def __init__(self):
        self.next_sequence = 1
        self.pending_by_recipient = {}

    def dispatch_batch(self, jobs):
        threads = []
        for job in jobs:
            worker = threading.Thread(target=self._queue_delivery, args=(job,))
            worker.start()
            threads.append(worker)

        for worker in threads:
            worker.join()

        return self.pending_by_recipient

    def _queue_delivery(self, job):
        recipient_queue = self.pending_by_recipient.setdefault(job["recipient_id"], [])

        sequence = self.next_sequence
        time.sleep(0.001)
        self.next_sequence = sequence + 1

        recipient_queue.append(
            {
                "sequence": sequence,
                "channel": job["channel"],
                "payload": job["payload"],
            }
        )
