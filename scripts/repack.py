"""下载、核验官方 APK，修改清单并使用固定证书签名。"""

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

from check_update import SOURCE_PACKAGE, validate_metadata


TARGET_PACKAGE = "com.hunantv.imgo.activity"
SOURCE_CERTIFICATE = "863ffbb78fec1d01f37f39f35f572fd99e2cb1d58bdaae70b7e85d90dad07257"
TARGET_CERTIFICATE = "ca495385f018fb307ecef37e8e181d7cb520469e34bbb05b0acae0dc8974e484"
ANDROID = "{http://schemas.android.com/apk/res/android}"
COMPONENTS = {"application", "activity", "activity-alias", "provider", "receiver", "service"}


def run(*command):
    return subprocess.run(
        command, check=True, capture_output=True, encoding="utf-8", errors="replace"
    ).stdout


def verify_certificate(path, expected):
    output = run("apksigner", "verify", "--verbose", "--print-certs", str(path))
    certificates = re.findall(r"Signer #\d+ certificate SHA-256 digest: ([a-f0-9]+)", output)
    if certificates != [expected]:
        raise ValueError("APK 签名证书与固定指纹不符")
    return output


def verify_source(path, api_md5, http_md5):
    content = path.read_bytes()
    md5 = hashlib.md5(content)
    if api_md5 and md5.hexdigest().lower() != api_md5.lower():
        raise ValueError("官方下载文件与更新接口的 MD5 不符")
    if http_md5 is not None and base64.b64encode(md5.digest()).decode("ascii") != http_md5.strip():
        raise ValueError("官方下载文件与响应头 Content-MD5 不符")
    report = verify_certificate(path, SOURCE_CERTIFICATE)
    if not api_md5:
        if not re.search(r"^Verified using v(?:2|3(?:\.1)?) scheme \([^\n]+\): true$", report, re.MULTILINE):
            raise ValueError("更新接口未给出 MD5，必须通过官方 APK v2 或 v3 内容签名校验")
        print("更新接口未给出 MD5，已通过固定官方证书及 APK 内容签名校验")
    return hashlib.sha256(content).hexdigest()


def read_identity(path):
    output = run("aapt", "dump", "badging", str(path))
    match = re.search(
        r"^package: name='([^']+)' versionCode='(\d+)' versionName='([^']+)'",
        output,
        re.MULTILINE,
    )
    if not match:
        raise ValueError("无法读取 APK 身份信息")
    return match.group(1), int(match.group(2)), match.group(3)


def rewrite_manifest(path):
    ET.register_namespace("android", ANDROID[1:-1])
    tree = ET.parse(path)
    manifest = tree.getroot()
    if manifest.get("package") != SOURCE_PACKAGE:
        raise ValueError("清单中的原始包名不符")
    for element in manifest.iter():
        if element.tag in COMPONENTS:
            for attribute in ("name", "targetActivity", "backupAgent", "appComponentFactory"):
                value = element.get(ANDROID + attribute)
                if value and (value.startswith(".") or "." not in value):
                    element.set(ANDROID + attribute, SOURCE_PACKAGE + "." + value.lstrip("."))
        for attribute, value in list(element.attrib.items()):
            package_reference = attribute in {
                ANDROID + "authorities", ANDROID + "permission", ANDROID + "readPermission",
                ANDROID + "writePermission", ANDROID + "taskAffinity",
            }
            permission_name = element.tag in {
                "permission", "uses-permission", "uses-permission-sdk-23",
                "permission-group", "permission-tree",
            } and attribute == ANDROID + "name"
            if (package_reference or permission_name) and (
                value == SOURCE_PACKAGE or value.startswith(SOURCE_PACKAGE + ".")
            ):
                element.set(attribute, TARGET_PACKAGE + value[len(SOURCE_PACKAGE):])
    manifest.set("package", TARGET_PACKAGE)
    manifest.find("application").set(ANDROID + "label", "飞牛音乐")
    tree.write(path, encoding="utf-8", xml_declaration=True)


def is_signature_file(name):
    name = name.upper()
    return name.startswith("META-INF/") and (
        name.endswith((".RSA", ".DSA", ".EC", ".SF")) or name == "META-INF/MANIFEST.MF"
    )


def main():
    work = Path("work")
    data = json.loads((work / "update.json").read_text(encoding="utf-8"))
    validate_metadata(data)
    version = data["versionName"].lstrip("vV")
    source = work / "official.apk"
    partial = source.with_suffix(".part")
    with urllib.request.urlopen(data["url"], timeout=60) as response, partial.open("wb") as output:
        http_md5 = response.headers.get("Content-MD5")
        shutil.copyfileobj(response, output)
    source_sha256 = verify_source(partial, data["md5"], http_md5)
    partial.replace(source)
    identity = read_identity(source)
    if identity != (SOURCE_PACKAGE, data["versionCode"], version):
        raise ValueError("APK 的实际包名或版本与更新接口不符")
    apktool = ("java", "-jar", os.environ["APKTOOL_JAR"])
    framework = work / "framework"
    decoded = work / "decoded"
    run(*apktool, "d", "--no-src", "--frame-path", str(framework), "-o", str(decoded), str(source))
    rewrite_manifest(decoded / "AndroidManifest.xml")
    rebuilt = work / "rebuilt.apk"
    run(*apktool, "b", "--frame-path", str(framework), "-o", str(rebuilt), str(decoded))
    with zipfile.ZipFile(rebuilt) as apk:
        manifest = apk.read("AndroidManifest.xml")
    unsigned = work / "unsigned.apk"
    # 仅使用新清单，其他条目直接取自官方原包，避免重编译资源产生额外差异。
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(unsigned, "w") as output:
        names = original.namelist()
        if len(names) != len(set(names)):
            raise ValueError("原包包含重复 ZIP 条目")
        for info in original.infolist():
            if not is_signature_file(info.filename):
                content = manifest if info.filename == "AndroidManifest.xml" else original.read(info.filename)
                output.writestr(info, content)
    aligned = work / "aligned.apk"
    run("zipalign", "-f", "-p", "4", str(unsigned), str(aligned))
    Path("dist").mkdir(exist_ok=True)
    final = Path("dist") / f"FN-Music-{version}-mango-universal.apk"
    run(
        "apksigner", "sign", "--ks", str(work / "release.jks"),
        "--ks-key-alias", "repackage", "--ks-pass", "env:KEYSTORE_PASSWORD",
        "--key-pass", "env:KEYSTORE_PASSWORD", "--out", str(final), str(aligned),
    )
    verify_certificate(final, TARGET_CERTIFICATE)
    run("zipalign", "-c", "-p", "4", str(final))
    if read_identity(final) != (TARGET_PACKAGE, data["versionCode"], version):
        raise ValueError("成品包名或版本不符")
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(final) as output:
        if output.testzip() is not None:
            raise ValueError("成品 ZIP 校验失败")
        for name in original.namelist():
            if name != "AndroidManifest.xml" and not is_signature_file(name):
                if original.read(name) != output.read(name):
                    raise ValueError(f"程序代码或资源出现额外变化 {name}")
        if any(not is_signature_file(name) for name in set(output.namelist()) - set(original.namelist())):
            raise ValueError("成品含额外条目")
    verified = work / "verified"
    run(*apktool, "d", "--no-src", "--frame-path", str(framework), "-o", str(verified), str(final))
    expected = ET.parse(decoded / "AndroidManifest.xml").getroot()
    actual = ET.parse(verified / "AndroidManifest.xml").getroot()
    actual.set("package", TARGET_PACKAGE)
    if [(e.tag, e.attrib) for e in expected.iter()] != [(e.tag, e.attrib) for e in actual.iter()]:
        raise ValueError("成品清单与预期不一致")
    digest = hashlib.sha256(final.read_bytes()).hexdigest()
    Path("dist/SHA256SUMS.txt").write_text(f"{digest}  {final.name}\n", encoding="utf-8")
    metadata = {
        "version": version, "versionCode": data["versionCode"],
        "package": TARGET_PACKAGE, "sourceMd5": data["md5"], "sourceSha256": source_sha256,
        "sha256": digest, "certificateSha256": TARGET_CERTIFICATE,
    }
    Path("dist/build.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    notes = (
        f"飞牛音乐 {version}，上游 versionCode `{data['versionCode']}`。\n\n"
        f"安装名称为飞牛音乐，包名为 `{TARGET_PACKAGE}`，使用固定自签名证书。\n\n"
        "本次已通过原包证书、文件哈希、成品签名、对齐及代码资源一致性检查。\n\n"
        "首次请通过 KomiStore 安装本仓库 APK，让商店关联后续更新。\n\n"
        "官方更新说明\n\n" + data.get("updateMessage", "") + "\n"
    )
    (work / "release-notes.md").write_text(notes, encoding="utf-8")
    print(f"构建与静态校验通过 {final.name}")


if __name__ == "__main__":
    main()
