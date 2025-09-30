ANY = object()


class Mocker:
    def __init__(self, *args, **kwargs):
        self._calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    # Provide minimal API used in tests; record calls for completeness.
    def register_uri(self, *args, **kwargs):
        self._calls.append((args, kwargs))

    def get(self, *args, **kwargs):
        self._calls.append((('GET',) + args, kwargs))

    def post(self, *args, **kwargs):
        self._calls.append((('POST',) + args, kwargs))

    def delete(self, *args, **kwargs):
        self._calls.append((('DELETE',) + args, kwargs))

    def put(self, *args, **kwargs):
        self._calls.append((('PUT',) + args, kwargs))

    # Allow attribute access for compatibility if tests expect .last_request, etc.
    @property
    def called(self):
        return bool(self._calls)
