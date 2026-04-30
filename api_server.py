import argparse
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import requests

from main import LoginExpiredError, load_config, parse_traffic, query_traffic


def build_traffic_response(include_details=False):
    config = load_config()
    data = query_traffic(config)
    result = parse_traffic(data)

    response = {
        "ok": True,
        "unit": "GB",
        "total_gb": round(result["total_gb"], 2),
        "used_gb": round(result["used_gb"], 2),
        "balance_gb": round(result["balance_gb"], 2),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    if include_details:
        response["details"] = result["details"]

    return response


class TrafficApiHandler(BaseHTTPRequestHandler):
    server_version = "TrafficApi/1.0"

    def do_GET(self):
        parsed_url = urlparse(self.path)

        if parsed_url.path == "/health":
            self.respond_json(200, {"ok": True})
            return

        if parsed_url.path not in ("/", "/traffic"):
            self.respond_json(404, {"ok": False, "error": "Not found"})
            return

        query = parse_qs(parsed_url.query)
        include_details = query.get("details", ["0"])[0].lower() in ("1", "true", "yes")

        try:
            self.respond_json(200, build_traffic_response(include_details))
        except LoginExpiredError as error:
            print_relogin_reminder(error)
            self.respond_json(
                401,
                {
                    "ok": False,
                    "error": "login_expired",
                    "message": "登录已过期，请重新登录并用 extract_curl_config.py 更新 config.json。",
                },
            )
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as error:
            self.respond_json(
                500,
                {
                    "ok": False,
                    "error": "config_error",
                    "message": str(error),
                },
            )
        except requests.RequestException as error:
            self.respond_json(
                502,
                {
                    "ok": False,
                    "error": "upstream_error",
                    "message": str(error),
                },
            )
        except Exception as error:
            self.respond_json(
                500,
                {
                    "ok": False,
                    "error": "server_error",
                    "message": str(error),
                },
            )

    def respond_json(self, status_code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{now}] {self.address_string()} {format % args}")


def print_relogin_reminder(error):
    print(f"\n{error}")
    print("登录信息已过期。请重新登录小程序，复制新的 curl，然后运行：")
    print("python extract_curl_config.py < curl.txt")


def run_server(host, port):
    server = ThreadingHTTPServer((host, port), TrafficApiHandler)
    print(f"流量查询 API 已启动：http://{host}:{port}/traffic")
    print(f"明细接口：http://{host}:{port}/traffic?details=1")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在停止 API 服务...")
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description="启动流量查询 GET API 服务。")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认 127.0.0.1。")
    parser.add_argument("--port", type=int, default=8000, help="监听端口，默认 8000。")
    args = parser.parse_args()

    run_server(args.host, args.port)


if __name__ == "__main__":
    main()
