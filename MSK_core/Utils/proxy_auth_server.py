import socket
import threading
import base64
import select


class LocalProxyAuthServer:
    """Tiny local HTTP proxy that forwards to an authenticated upstream proxy.

    The browser connects to 127.0.0.1:<local_port> without credentials.
    This server adds Proxy-Authorization headers when forwarding to the
    real upstream proxy (e.g. gw.dataimpulse.com:10000).
    """

    def __init__(self, upstream_host, upstream_port, username, password):
        self._upstream_host = upstream_host
        self._upstream_port = int(upstream_port)
        self._resolved_ip = None
        self._resolve_lock = threading.Lock()
        try:
            self._resolved_ip = socket.gethostbyname(self._upstream_host)
        except Exception:
            pass
        self._auth_header = (
            b"Proxy-Authorization: Basic "
            + base64.b64encode(f"{username}:{password}".encode())
            + b"\r\n"
        )
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("127.0.0.1", 0))
        self.port = self._server.getsockname()[1]
        self._server.listen(64)
        self._server.settimeout(1.0)
        self._running = True
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    @property
    def address(self):
        return f"127.0.0.1:{self.port}"

    def _get_upstream_addr(self):
        """Resolve upstream host, using cached IP when available."""
        if self._resolved_ip:
            return self._resolved_ip, self._upstream_port
        with self._resolve_lock:
            if self._resolved_ip:
                return self._resolved_ip, self._upstream_port
            try:
                self._resolved_ip = socket.gethostbyname(self._upstream_host)
            except Exception:
                return self._upstream_host, self._upstream_port
        return self._resolved_ip, self._upstream_port

    def _accept_loop(self):
        while self._running:
            try:
                client, _ = self._server.accept()
                t = threading.Thread(target=self._handle_client, args=(client,), daemon=True)
                t.start()
            except socket.timeout:
                continue
            except OSError:
                break

    def _connect_upstream(self):
        """Connect to upstream proxy with retry logic."""
        host, port = self._get_upstream_addr()
        last_err = None
        for attempt in range(3):
            try:
                upstream = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                upstream.settimeout(60)
                upstream.connect((host, port))
                return upstream
            except Exception as e:
                last_err = e
                try:
                    upstream.close()
                except Exception:
                    pass
                if attempt < 2:
                    with self._resolve_lock:
                        try:
                            self._resolved_ip = socket.gethostbyname(self._upstream_host)
                            host = self._resolved_ip
                        except Exception:
                            pass
                    import time
                    time.sleep(0.5)
        raise last_err or ConnectionError(f"Cannot connect to {self._upstream_host}:{self._upstream_port}")

    def _handle_client(self, client):
        upstream = None
        try:
            client.settimeout(60)
            data = b""
            while b"\r\n\r\n" not in data:
                chunk = client.recv(8192)
                if not chunk:
                    return
                data += chunk

            header_end = data.index(b"\r\n\r\n")
            header_block = data[: header_end]
            body = data[header_end + 4:]  # everything AFTER \r\n\r\n

            first_line_end = header_block.index(b"\r\n")
            first_line = header_block[:first_line_end]
            rest_headers = header_block[first_line_end:]  # starts with \r\n

            is_connect = first_line.upper().startswith(b"CONNECT")

            # Reconstruct: request-line + original headers + auth header + \r\n\r\n + body
            injected = first_line + rest_headers + b"\r\n" + self._auth_header + b"\r\n" + body

            upstream = self._connect_upstream()
            upstream.sendall(injected)

            if is_connect:
                response = b""
                while b"\r\n\r\n" not in response:
                    chunk = upstream.recv(8192)
                    if not chunk:
                        return
                    response += chunk

                # Check if upstream accepted the CONNECT
                status_line = response.split(b"\r\n", 1)[0]
                if b"200" not in status_line:
                    # Upstream rejected -- forward error to browser and bail
                    client.sendall(response)
                    return

                # Split response: headers go to client, any extra bytes
                # after \r\n\r\n are the start of the SSL handshake
                resp_header_end = response.index(b"\r\n\r\n") + 4
                client.sendall(response[:resp_header_end])
                trailing = response[resp_header_end:]
                if trailing:
                    client.sendall(trailing)

            self._relay(client, upstream)
        except Exception:
            pass
        finally:
            try:
                client.close()
            except Exception:
                pass
            try:
                if upstream:
                    upstream.close()
            except Exception:
                pass

    def _relay(self, sock_a, sock_b):
        sockets = [sock_a, sock_b]
        while self._running:
            try:
                readable, _, errored = select.select(sockets, [], sockets, 10)
            except Exception:
                break
            if errored:
                break
            for s in readable:
                try:
                    data = s.recv(65536)
                    if not data:
                        return
                    target = sock_b if s is sock_a else sock_a
                    target.sendall(data)
                except Exception:
                    return

    def stop(self):
        self._running = False
        try:
            self._server.close()
        except Exception:
            pass

