import json
import requests
from datetime import datetime
from pathlib import Path

URL = "https://wx.10099.com.cn/contact-web/api/busi/qryUserRes"
CONFIG_FILE = Path(__file__).with_name("config.json")
CONFIG_KEYS = ("Session", "Access", "User-Agent", "data")

BASE_HEADERS = {
    "Host": "wx.10099.com.cn",
    "content-type": "application/json",
    "Accept-Encoding": "gzip,compress,br,deflate",
    "Referer": "https://servicewechat.com/wxfa72ff5488bbd1d9/125/page-frame.html",
}

LOGIN_EXPIRED_KEYWORDS = (
    "登录",
    "过期",
    "失效",
    "重新",
    "未授权",
    "认证",
    "无效",
    "session",
    "access",
    "token",
)


class LoginExpiredError(RuntimeError):
    pass


def kb_to_gb(value):
    return int(value) / 1024 / 1024


def load_config():
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(
            f"未找到 {CONFIG_FILE}，请先运行 extract_curl_config.py 生成配置。"
        )

    with CONFIG_FILE.open("r", encoding="utf-8") as file:
        config = json.load(file)

    missing_keys = [key for key in CONFIG_KEYS if not str(config.get(key, "")).strip()]
    if missing_keys:
        raise ValueError(f"{CONFIG_FILE} 缺少必要字段：{', '.join(missing_keys)}")

    return {key: str(config[key]).strip() for key in CONFIG_KEYS}


def build_headers(config):
    headers = BASE_HEADERS.copy()
    headers["Session"] = config["Session"]
    headers["Access"] = config["Access"]
    headers["User-Agent"] = config["User-Agent"]
    return headers


def query_traffic(config):
    resp = requests.post(
        URL,
        headers=build_headers(config),
        json={"data": config["data"]},
        timeout=10,
    )
    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:
        if resp.status_code in (401, 403):
            raise LoginExpiredError(f"HTTP {resp.status_code}") from exc
        raise

    return resp.json()


def is_login_expired(data):
    status = str(data.get("status", ""))
    message = str(data.get("message") or data.get("msg") or "")
    text = f"{status} {message}".lower()
    return any(keyword in text for keyword in LOGIN_EXPIRED_KEYWORDS)


def parse_traffic(data):
    if data.get("status") != "000000":
        if is_login_expired(data):
            message = data.get("message") or data.get("msg") or data.get("status")
            raise LoginExpiredError(f"登录已过期或认证失败：{message}")
        raise RuntimeError(f"接口返回异常：{data.get('message')}")

    user_res_list = (
        data.get("data", {})
        .get("intfResultBean", {})
        .get("userResList", [])
    )

    total_kb = 0
    balance_kb = 0
    used_kb = 0

    details = []

    for item in user_res_list:
        name = item.get("itemName", "")
        total = int(item.get("highFee", 0))
        balance = int(item.get("balance", 0))
        used = int(item.get("addupValue", 0))

        total_kb += total
        balance_kb += balance
        used_kb += used

        details.append({
            "name": name,
            "total_gb": kb_to_gb(total),
            "balance_gb": kb_to_gb(balance),
            "used_gb": kb_to_gb(used),
            "start": item.get("startTime"),
            "end": item.get("endTime"),
        })

    return {
        "total_gb": kb_to_gb(total_kb),
        "balance_gb": kb_to_gb(balance_kb),
        "used_gb": kb_to_gb(used_kb),
        "details": details,
    }


def print_traffic(result):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"\n[{now}] 中国广电流量")
    print(f"总流量：{result['total_gb']:.2f} GB")
    print(f"剩余：{result['balance_gb']:.2f} GB")
    print(f"已用：{result['used_gb']:.2f} GB")

    print("\n明细：")
    for item in result["details"]:
        print(
            f"- {item['name']}："
            f"总 {item['total_gb']:.2f} GB，"
            f"剩余 {item['balance_gb']:.2f} GB，"
            f"已用 {item['used_gb']:.2f} GB，"
            f"有效期 {item['start']} ~ {item['end']}"
        )


def wait_for_relogin(error):
    print(f"\n{error}")
    print("请重新登录小程序，复制新的 curl，然后运行：")
    print("python extract_curl_config.py < curl.txt")
    print("更新 config.json 后按回车重试，按 Ctrl+C 退出。")
    try:
        input()
    except EOFError as exc:
        raise SystemExit(
            "未检测到可交互输入，登录信息已过期，请更新 config.json 后重新运行。"
        ) from exc


if __name__ == "__main__":
    while True:
        try:
            config = load_config()
            data = query_traffic(config)
            result = parse_traffic(data)
            print_traffic(result)
            break
        except LoginExpiredError as error:
            wait_for_relogin(error)
