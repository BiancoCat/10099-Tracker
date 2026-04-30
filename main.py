import requests
import time
from datetime import datetime

URL = "https://wx.10099.com.cn/contact-web/api/busi/qryUserRes"

HEADERS = {
    "Host": "wx.10099.com.cn",
    "Session": "8a670f4d15be0af224ee1004d7b12a80",
    "Access": "847d5bc222d1f8ed1d715067b20d3224",
    "content-type": "application/json",
    "Accept-Encoding": "gzip,compress,br,deflate",
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 26_4 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
        "MicroMessenger/8.0.70(0x1800463a) NetType/WIFI Language/zh_CN"
    ),
    "Referer": "https://servicewechat.com/wxfa72ff5488bbd1d9/125/page-frame.html",
}

PAYLOAD = {
    "data": "xJOqHMJ6wGEstble8V6FS8FduN30P00DBzKATxe+EMYuqj4FEmdVDRQVwwcx6ojONxXQcfEOyu/uipB+pn8fztCm1Vl+79Y9C+lMpV2iSsop5gpzGcR3CZKp6AUfAo1OF3e/IhcKPKYdCQTO3X8m/C0DZiBiO6sn4qd8rnEVo9/RhU1MNfKwNhbsGs93Dzh436aRj+whegaJ/wIzLEMJjXTvBjYugu1ORfX+L1ftW5zvlDrou+kSNUK6v/HqkHsQGRUvRGUSYy1tEBMKkj4aqWqJQlMVB59lCyuTakC69M/2d1aAgQkPPPN4eDeMH80dumXRYtivXooHT0iMfs2tVw=="
}


def kb_to_gb(value):
    return int(value) / 1024 / 1024


def query_traffic():
    resp = requests.post(URL, headers=HEADERS, json=PAYLOAD, timeout=10)
    resp.raise_for_status()
    return resp.json()


def parse_traffic(data):
    if data.get("status") != "000000":
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


if __name__ == "__main__":
    data = query_traffic()
    result = parse_traffic(data)
    print_traffic(result)