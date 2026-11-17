"""Q2 - Notification System: preferences, 3 channels, history, retry with backoff.
Run: python q2_notification_system.py
"""
import random
import time
from collections import deque

RETRY_DELAYS = [0.1, 0.2, 0.4, 0.8]  # seconds here; 10s, 1m, 5m, 30m in production
MAX_ATTEMPTS = len(RETRY_DELAYS) + 1


class Channel:
    """Base channel. Real versions call SES/SendGrid, Twilio, FCM/APNs."""
    name = "base"

    def __init__(self, failure_rate=0.0):
        self.failure_rate = failure_rate

    def send(self, user, message):
        if random.random() < self.failure_rate:
            raise ConnectionError(f"{self.name} provider timeout")
        print(f"    -> {self.name.upper()} to {user['name']}: {message}")


class EmailChannel(Channel): name = "email"
class SMSChannel(Channel): name = "sms"
class PushChannel(Channel): name = "push"


TEMPLATES = {
    "order_update": "Order {order_id} update: {status}",
    "alert": "ALERT: {text}",
    "reminder": "Reminder: {text}",
}
# type -> default channels
TYPE_CHANNELS = {"order_update": ["push", "sms"], "alert": ["sms", "email", "push"],
                 "reminder": ["push"]}


class NotificationService:
    def __init__(self, channels):
        self.channels = {c.name: c for c in channels}
        self.users = {}
        self.queue = deque()
        self.history = []     # notification history + delivery status
        self.dlq = []         # dead letter queue

    def register_user(self, user_id, name, prefs):
        """prefs: {'email': True, 'sms': False, 'push': True, 'muted_types': []}"""
        self.users[user_id] = {"name": name, "prefs": prefs}

    def send(self, user_id, ntype, **data):
        message = TEMPLATES[ntype].format(**data)
        user = self.users[user_id]
        for ch in TYPE_CHANNELS[ntype]:
            if ntype in user["prefs"].get("muted_types", []) or not user["prefs"].get(ch, False):
                self._log(user_id, ntype, ch, "SKIPPED", 0)
                continue
            self.queue.append({"user_id": user_id, "type": ntype, "channel": ch,
                               "message": message, "attempt": 0})

    def process(self):
        while self.queue:
            job = self.queue.popleft()
            user = self.users[job["user_id"]]
            job["attempt"] += 1
            try:
                self.channels[job["channel"]].send(user, job["message"])
                self._log(job["user_id"], job["type"], job["channel"], "SENT", job["attempt"])
            except ConnectionError as e:
                if job["attempt"] >= MAX_ATTEMPTS:
                    self._log(job["user_id"], job["type"], job["channel"], "FAILED", job["attempt"])
                    self.dlq.append(job)
                else:
                    delay = RETRY_DELAYS[job["attempt"] - 1] + random.random() * 0.05  # jitter
                    print(f"    !! {e}; retry {job['attempt']} in {delay:.2f}s")
                    time.sleep(delay)
                    self.queue.append(job)   # real system: delayed retry queue

    def _log(self, user_id, ntype, channel, status, attempts):
        self.history.append({"user": user_id, "type": ntype, "channel": channel,
                             "status": status, "attempts": attempts})

    def get_history(self, user_id):
        return [h for h in self.history if h["user"] == user_id]


if __name__ == "__main__":
    random.seed(4)  # this seed makes the SMS provider fail a few times, so retries are visible
    svc = NotificationService([EmailChannel(), SMSChannel(failure_rate=0.6), PushChannel()])
    svc.register_user(1, "Asha", {"email": True, "sms": True, "push": True})
    svc.register_user(2, "Ravi", {"email": True, "sms": False, "push": True, "muted_types": ["reminder"]})

    svc.send(1, "order_update", order_id=42, status="Out for delivery")
    svc.send(1, "alert", text="New login detected")
    svc.send(2, "reminder", text="Complete your payment")
    svc.send(2, "order_update", order_id=43, status="Delivered")
    svc.process()

    print("\nHistory for user 1:")
    for h in svc.get_history(1):
        print("  ", h)
    print("History for user 2:")
    for h in svc.get_history(2):
        print("  ", h)
    print("Dead letter queue size:", len(svc.dlq))
