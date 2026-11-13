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
    data = result["data"]
    validate_metadata(data)
    return data


def validate_metadata(data):
    url = urllib.parse.urlsplit(data["url"])
    version = data["versionName"].lstrip("vV")
    if (
        data["package"] != SOURCE_PACKAGE
        or url.scheme != "https"
        or url.netloc != "apppkg.fnnas.com"
        or not url.path.endswith(".apk")
        or type(data["versionCode"]) is not int
        or data["versionCode"] <= 0
        or not re.fullmatch(r"\d+\.\d+\.\d+", version)
        or not re.fullmatch(r"[a-fA-F0-9]{32}", data["md5"])
    ):
        raise ValueError("官方更新元数据不符合已验证的格式")


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
