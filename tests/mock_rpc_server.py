from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json


GENESIS = "4f95857586e2c66063c277370eda99cd75897d773af09f0c3cd1e22f7e87db39"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length))
        method = request.get("method")
        if method == "get_info":
            result = {"status": "OK", "mainnet": True, "version": "2.0.2-release"}
        elif method == "get_block_header_by_height":
            result = {"status": "OK", "block_header": {"hash": GENESIS}}
        elif method == "get_connections":
            result = {"status": "OK", "connections": [
                {"host": "81.2.69.160", "state": "normal", "peer_id": "0000000000000001", "address_type": "IPv4"},
                {"host": "81.2.69.160", "state": "idle", "peer_id": "0000000000000002", "address_type": "IPv4"},
                {"host": "10.0.0.8", "state": "normal", "peer_id": "0000000000000003", "address_type": "IPv4"}
            ]}
        else:
            self.send_response(404); self.end_headers(); return
        response = json.dumps({"jsonrpc": "2.0", "id": request.get("id"), "result": result}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)


ThreadingHTTPServer(("0.0.0.0", 8197), Handler).serve_forever()
