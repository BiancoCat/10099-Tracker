import argparse
import json
import re
import shlex
import sys
from pathlib import Path


CONFIG_KEYS = ("Session", "Access", "User-Agent", "data")
DEFAULT_OUTPUT = Path(__file__).with_name("config.json")


def read_interactive_paste():
    print("请粘贴完整 curl 命令，粘贴完成后输入空行结束：", flush=True)
    lines = []

    while True:
        try:
            line = input()
        except EOFError:
            break

        if not line.strip():
            break
        lines.append(line)

    return "\n".join(lines)


def read_curl_text(path, paste=False):
    if path:
        return Path(path).read_text(encoding="utf-8")

    if paste or sys.stdin.isatty():
        return read_interactive_paste()

    return sys.stdin.read()


def iter_option_values(args, option_names):
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in option_names and index + 1 < len(args):
            yield args[index + 1]
            index += 2
            continue

        for option_name in option_names:
            prefix = f"{option_name}="
            if arg.startswith(prefix):
                yield arg[len(prefix):]
                break

        index += 1


def parse_headers(args):
    headers = {}
    for header in iter_option_values(args, ("-H", "--header")):
        if ":" not in header:
            continue
        name, value = header.split(":", 1)
        headers[name.strip().lower()] = value.strip()
    return headers


def extract_data(args):
    for raw_data in iter_option_values(
        args,
        ("--data", "--data-raw", "--data-binary", "--data-ascii", "-d"),
    ):
        try:
            payload = json.loads(raw_data)
        except json.JSONDecodeError:
            continue

        data = payload.get("data")
        if data:
            return str(data).strip()

    return ""


def extract_user_agent(args, headers):
    user_agent = headers.get("user-agent")
    if user_agent:
        return user_agent

    for value in iter_option_values(args, ("-A", "--user-agent")):
        if value:
            return value.strip()

    for arg in args:
        if arg.startswith("-A") and len(arg) > 2:
            return arg[2:].strip()

    return ""


def normalize_curl_text(curl_text):
    return re.sub(r"\\\s*(?:\r?\n|\\n)\s*", " ", curl_text)


def extract_config(curl_text):
    args = shlex.split(normalize_curl_text(curl_text))
    headers = parse_headers(args)
    config = {
        "Session": headers.get("session", ""),
        "Access": headers.get("access", ""),
        "User-Agent": extract_user_agent(args, headers),
        "data": extract_data(args),
    }

    missing_keys = [key for key in CONFIG_KEYS if not config[key]]
    if missing_keys:
        raise ValueError(f"curl 中缺少必要字段：{', '.join(missing_keys)}")

    return config


def main():
    parser = argparse.ArgumentParser(
        description="从 curl 命令中提取 Session、Access、User-Agent、data 并写入 config.json。"
    )
    parser.add_argument(
        "curl_file",
        nargs="?",
        help="保存 curl 命令的文本文件；不传则从标准输入读取。",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="配置输出路径，默认写入当前脚本同目录的 config.json。",
    )
    parser.add_argument(
        "--paste",
        action="store_true",
        help="进入交互粘贴模式，粘贴 curl 后输入空行结束。",
    )
    args = parser.parse_args()

    curl_text = read_curl_text(args.curl_file, args.paste)
    if not curl_text.strip():
        raise SystemExit("未读取到 curl 内容。")

    config = extract_config(curl_text)

    output = Path(args.output)
    output.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"已更新 {output}")


if __name__ == "__main__":
    main()
