class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
    def json(self):
        return self._payload
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

class FakeSession:
    """Gibt vorgegebene Antworten zurueck und zaehlt Aufrufe."""
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        return self._responses.pop(0)
