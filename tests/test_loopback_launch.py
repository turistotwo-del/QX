"""Desktop HTTP startup must not release its port before Uvicorn takes it."""
import socket
import unittest
from urllib.request import urlopen

from fastapi import FastAPI
from modern.start import _start_loopback_server


class LoopbackLaunchTests(unittest.TestCase):
    def test_http_server_receives_the_prebound_socket(self):
        app = FastAPI()

        @app.get('/api/health')
        def health():
            return {'ok': True}

        server, thread, listener, url = _start_loopback_server(app, timeout=5)
        try:
            self.assertTrue(thread.is_alive())
            self.assertEqual(listener.getsockname()[0], '127.0.0.1')
            with urlopen(url + 'api/health', timeout=2) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(b'true', response.read())
            # The active socket is retained for the lifetime of the server:
            # another process cannot bind and hijack its port.
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as contender:
                with self.assertRaises(OSError):
                    contender.bind(listener.getsockname())
        finally:
            server.should_exit = True
            thread.join(timeout=5)
            listener.close()
        self.assertFalse(thread.is_alive())
        self.assertEqual(listener.fileno(), -1)

    def test_missing_health_route_is_error_and_does_not_leave_server_running(self):
        # A syntactically valid app can still be unusable. Never proceed to a
        # blank window because some other endpoint happens to answer.
        app = FastAPI()
        with self.assertRaisesRegex(RuntimeError, 'не ответил'):
            _start_loopback_server(app, timeout=.5)


if __name__ == '__main__':
    unittest.main()
