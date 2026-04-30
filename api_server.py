import argparse
import json
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, quote, urlencode, urlparse, urlunparse

import requests

from extract_curl_config import extract_config
from main import CONFIG_FILE, CONFIG_KEYS, LoginExpiredError, load_config, parse_traffic, query_traffic


WEB_DIR = Path(__file__).with_name("web")
INDEX_FILE = WEB_DIR / "index.html"
ICON_FILE = WEB_DIR / "icon.svg"
OPTIONAL_CONFIG_DEFAULTS = {
    "bark_enabled": False,
    "bark_url": "",
    "bark_icon_url": "",
    "bark_cooldown_seconds": 300,
}
OPTIONAL_CONFIG_KEYS = tuple(OPTIONAL_CONFIG_DEFAULTS)
LAST_BARK_NOTICE_AT = {}


def parse_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def read_raw_config():
    if not CONFIG_FILE.exists():
        return {}

    with CONFIG_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def normalize_saved_config(config):
    ordered_config = {}
    for key in CONFIG_KEYS:
        ordered_config[key] = str(config.get(key, "")).strip()

    ordered_config["bark_enabled"] = parse_bool(config.get("bark_enabled", False))
    ordered_config["bark_url"] = str(config.get("bark_url", "")).strip()
    ordered_config["bark_icon_url"] = str(config.get("bark_icon_url", "")).strip()
    try:
        ordered_config["bark_cooldown_seconds"] = max(
            0,
            int(config.get("bark_cooldown_seconds", 300)),
        )
    except (TypeError, ValueError):
        ordered_config["bark_cooldown_seconds"] = 300

    for key, value in config.items():
        if key not in ordered_config:
            ordered_config[key] = value

    return ordered_config


def write_raw_config(config):
    CONFIG_FILE.write_text(
        json.dumps(normalize_saved_config(config), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def get_config_for_api():
    config = read_raw_config()
    for key, value in OPTIONAL_CONFIG_DEFAULTS.items():
        config.setdefault(key, value)
    return normalize_saved_config(config)


def update_config(payload):
    config = read_raw_config()
    allowed_keys = (*CONFIG_KEYS, *OPTIONAL_CONFIG_KEYS)

    for key in allowed_keys:
        if key not in payload:
            continue
        if key == "bark_enabled":
            config[key] = parse_bool(payload[key])
        elif key == "bark_cooldown_seconds":
            config[key] = max(0, int(payload[key] or 0))
        else:
            config[key] = str(payload[key]).strip()

    missing_keys = [
        key for key in CONFIG_KEYS if not str(config.get(key, "")).strip()
    ]
    if missing_keys:
        raise ValueError(f"配置缺少必要字段：{', '.join(missing_keys)}")

    write_raw_config(config)
    return get_config_for_api()


def merge_curl_config(curl_text):
    config = read_raw_config()
    config.update(extract_config(curl_text))
    write_raw_config(config)
    return get_config_for_api()


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


def build_bark_url(bark_url, title, message, icon_url=""):
    bark_url = bark_url.strip()
    icon_url = icon_url.strip()
    encoded_title = quote(title, safe="")
    encoded_message = quote(message, safe="")
    encoded_icon = quote(icon_url, safe="")

    if (
        "{title}" in bark_url
        or "{message}" in bark_url
        or "{body}" in bark_url
        or "{icon}" in bark_url
    ):
        return (
            bark_url.replace("{title}", encoded_title)
            .replace("{message}", encoded_message)
            .replace("{body}", encoded_message)
            .replace("{icon}", encoded_icon)
        )

    if not bark_url.startswith(("http://", "https://")):
        bark_url = f"https://api.day.app/{quote(bark_url, safe='')}"

    parsed_url = urlparse(bark_url)
    path = f"{parsed_url.path.rstrip('/')}/{encoded_title}/{encoded_message}"
    query_items = parse_qsl(parsed_url.query, keep_blank_values=True)
    if icon_url:
        query_items.append(("icon", icon_url))

    return urlunparse(
        (
            parsed_url.scheme,
            parsed_url.netloc,
            path,
            "",
            urlencode(query_items),
            parsed_url.fragment,
        )
    )


def send_bark_notification(title, message, force=False):
    config = get_config_for_api()
    if not config.get("bark_enabled"):
        return {"sent": False, "reason": "bark_disabled"}
    if not config.get("bark_url"):
        return {"sent": False, "reason": "missing_bark_url"}

    cooldown = int(config.get("bark_cooldown_seconds", 300))
    now = time.time()
    notice_key = f"{title}:{message}"
    last_notice_at = LAST_BARK_NOTICE_AT.get(notice_key, 0)
    if not force and cooldown and now - last_notice_at < cooldown:
        return {"sent": False, "reason": "cooldown"}

    url = build_bark_url(
        config["bark_url"],
        title,
        message,
        config.get("bark_icon_url", ""),
    )
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    LAST_BARK_NOTICE_AT[notice_key] = now
    return {"sent": True}


def notify_api_error(error_type, message):
    title = f"流量 API 出错：{error_type}"
    try:
        result = send_bark_notification(title, message)
        if not result["sent"]:
            print(f"Bark 未发送：{result['reason']}")
    except Exception as error:
        print(f"Bark 发送失败：{error}")


class TrafficApiHandler(BaseHTTPRequestHandler):
    server_version = "TrafficApi/1.0"

    def do_GET(self):
        parsed_url = urlparse(self.path)

        if parsed_url.path in ("/", "/index.html"):
            self.respond_file(INDEX_FILE, "text/html; charset=utf-8")
            return

        if parsed_url.path in ("/icon.svg", "/favicon.svg"):
            self.respond_file(ICON_FILE, "image/svg+xml; charset=utf-8")
            return

        if parsed_url.path == "/health":
            self.respond_json(200, {"ok": True})
            return

        if parsed_url.path == "/api/config":
            try:
                self.respond_json(200, {"ok": True, "config": get_config_for_api()})
            except (ValueError, json.JSONDecodeError) as error:
                notify_api_error("config_error", str(error))
                self.respond_json(
                    500,
                    {
                        "ok": False,
                        "error": "config_error",
                        "message": str(error),
                    },
                )
            return

        if parsed_url.path != "/traffic":
            self.respond_json(404, {"ok": False, "error": "Not found"})
            return

        query = parse_qs(parsed_url.query)
        include_details = query.get("details", ["0"])[0].lower() in ("1", "true", "yes")

        try:
            self.respond_json(200, build_traffic_response(include_details))
        except LoginExpiredError as error:
            print_relogin_reminder(error)
            notify_api_error("login_expired", str(error))
            self.respond_json(
                401,
                {
                    "ok": False,
                    "error": "login_expired",
                    "message": "登录已过期，请重新登录并用 extract_curl_config.py 更新 config.json。",
                },
            )
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as error:
            notify_api_error("config_error", str(error))
            self.respond_json(
                500,
                {
                    "ok": False,
                    "error": "config_error",
                    "message": str(error),
                },
            )
        except requests.RequestException as error:
            notify_api_error("upstream_error", str(error))
            self.respond_json(
                502,
                {
                    "ok": False,
                    "error": "upstream_error",
                    "message": str(error),
                },
            )
        except Exception as error:
            notify_api_error("server_error", str(error))
            self.respond_json(
                500,
                {
                    "ok": False,
                    "error": "server_error",
                    "message": str(error),
                },
            )

    def do_POST(self):
        parsed_url = urlparse(self.path)

        try:
            if parsed_url.path == "/api/config":
                self.respond_json(200, {"ok": True, "config": update_config(self.read_json())})
                return

            if parsed_url.path == "/api/extract-curl":
                payload = self.read_json()
                curl_text = str(payload.get("curl", "")).strip()
                if not curl_text:
                    raise ValueError("curl 内容不能为空。")
                self.respond_json(200, {"ok": True, "config": merge_curl_config(curl_text)})
                return

            if parsed_url.path == "/api/test-bark":
                payload = self.read_json()
                if payload:
                    update_config(payload)

                result = send_bark_notification(
                    "流量 API 测试",
                    "Bark 通知配置正常。",
                    force=True,
                )
                self.respond_json(200, {"ok": True, **result})
                return

            self.respond_json(404, {"ok": False, "error": "Not found"})
        except (ValueError, json.JSONDecodeError) as error:
            self.respond_json(
                400,
                {
                    "ok": False,
                    "error": "bad_request",
                    "message": str(error),
                },
            )
        except requests.RequestException as error:
            self.respond_json(
                502,
                {
                    "ok": False,
                    "error": "bark_error",
                    "message": str(error),
                },
            )
        except Exception as error:
            notify_api_error("server_error", str(error))
            self.respond_json(
                500,
                {
                    "ok": False,
                    "error": "server_error",
                    "message": str(error),
                },
            )

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        if not length:
            return {}
        body = self.rfile.read(length).decode("utf-8")
        return json.loads(body)

    def respond_json(self, status_code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def respond_file(self, path, content_type):
        if not path.exists():
            self.respond_json(
                500,
                {
                    "ok": False,
                    "error": "missing_file",
                    "message": f"未找到 {path}",
                },
            )
            return

        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
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
    print(f"配置页面：http://{host}:{port}/")
    print(f"流量查询 API：http://{host}:{port}/traffic")
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
