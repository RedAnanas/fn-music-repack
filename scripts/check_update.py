"""查询官方更新并判断当前版本是否需要发布。"""

import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request


UPDATE_URL = "https://appversion.fnnas.com/api/v1/check-update"
SOURCE_PACKAGE = "com.trim.music"


def query_update():
    body = json.dumps(
        {"package": SOURCE_PACKAGE, "platform": "android"}, separators=(",", ":")
    )
    nonce = str(secrets.randbelow(900000) + 100000)
    timestamp = str(int(time.time() * 1000))
    body_digest = hashlib.md5(body.encode()).hexdigest()
    sign_content = "_".join(
        (
            os.environ["UPDATE_SIGN_PREFIX"],
            "/api/v1/check-update",
            nonce,
            timestamp,
            body_digest,
            os.environ["UPDATE_API_KEY"],
        )
    )
    signature = hashlib.md5(sign_content.encode()).hexdigest()
    request = urllib.request.Request(
        UPDATE_URL,
        data=body.encode(),
        headers={
            "Content-Type": "application/json",
            "authx": f"nonce={nonce}&timestamp={timestamp}&sign={signature}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    if result.get("code") == 404:
        return None
    if result.get("code") != 0:
        raise ValueError(f"更新查询失败，错误码 {result.get('code')}")
    data = result.get("data")
    validate_metadata(data)
    return data


def validate_metadata(data):
    if not isinstance(data, dict):
        raise ValueError("更新字段 data 不是对象")
    if data.get("package") != SOURCE_PACKAGE:
        raise ValueError("更新字段 package 与飞牛音乐包名不符")
    if not isinstance(data.get("url"), str):
        raise ValueError("更新字段 url 不是字符串")
    try:
        url = urllib.parse.urlsplit(data["url"])
    except ValueError:
        raise ValueError("更新字段 url 格式无效") from None
    if url.scheme != "https" or not url.path.endswith(".apk"):
        raise ValueError("更新字段 url 必须是 HTTPS 的 .apk 地址")
    if url.netloc not in {"apppkg.fnnas.com", "iso.liveupdate.fnnas.com"}:
        raise ValueError(f"更新字段 url 不在允许的下载来源内，主机名：{url.hostname!a}")
    code = data.get("versionCode")
    if type(code) is not int or code <= 0:
        raise ValueError("更新字段 versionCode 必须是正整数")
    version = data.get("versionName")
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version.lstrip("vV")):
        raise ValueError("更新字段 versionName 不是三段版本号")
    md5 = data.get("md5")
    if not isinstance(md5, str) or not re.fullmatch(r"[a-fA-F0-9]{32}", md5):
        if not isinstance(md5, str):
            raise ValueError(f"更新字段 md5 缺失或类型错误：{type(md5).__name__}")
        groups = [len(group) for group in re.findall(r"[a-fA-F0-9]+", md5)[:6]]
        raise ValueError(
            f"更新字段 md5 格式错误（版本 {version}/{code}，长度 {len(md5)}，"
            f"去除首尾空白后 {len(md5.strip())}，十六进制片段长度 {groups}，"
            f"含 sha256 字段：{'sha256' in data}）"
        )


def get_release(suffix):
    request = urllib.request.Request(
        f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/releases/{suffix}",
        headers={
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def main():
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        data = query_update()
        if data is None:
            output.write("build=false\n")
            print("官方接口暂未提供版本")
            return
        version = data["versionName"].lstrip("vV")
        tag = f"v{version}-{data['versionCode']}"
        release = get_release("tags/" + urllib.parse.quote(tag, safe=""))
        if release and not release["draft"]:
            output.write("build=false\n")
            print(f"{tag} 已发布")
            return
        latest = get_release("latest")
        if latest:
            match = re.search(r"-(\d+)$", latest["tag_name"])
            if match and int(match.group(1)) > data["versionCode"]:
                output.write("build=false\n")
                print("本次接口版本低于已发布版本，跳过")
                return
        Path("work").mkdir(exist_ok=True)
        Path("work/update.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        output.write(f"build=true\ntag={tag}\nversion={version}\n")
        print(f"准备构建 {tag}")


if __name__ == "__main__":
    main()
