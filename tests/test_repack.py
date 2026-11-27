"""核对改包边界与更新元数据校验。"""

from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_update import validate_metadata
from repack import ANDROID, SOURCE_PACKAGE, TARGET_PACKAGE, rewrite_manifest


class RepackTests(unittest.TestCase):
    def test_保留程序类名并修改包标识(self):
        text = '''<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="com.trim.music">
        <permission android:name="com.trim.music.INTERNAL"/>
        <uses-permission android:name="com.trim.music.INTERNAL"/>
        <application android:name=".App" android:label="旧名称">
        <activity android:name="com.trim.music.MainActivity"/>
        <provider android:name=".Files" android:authorities="com.trim.music.files"/>
        </application></manifest>'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "AndroidManifest.xml"
            path.write_text(text, encoding="utf-8")
            rewrite_manifest(path)
            manifest = ET.parse(path).getroot()
        self.assertEqual(manifest.get("package"), TARGET_PACKAGE)
        self.assertEqual(manifest.find("application").get(ANDROID + "name"), SOURCE_PACKAGE + ".App")
        self.assertEqual(manifest.find("application/activity").get(ANDROID + "name"), SOURCE_PACKAGE + ".MainActivity")
        self.assertEqual(manifest.find("application/provider").get(ANDROID + "authorities"), TARGET_PACKAGE + ".files")
        self.assertEqual(manifest.find("uses-permission").get(ANDROID + "name"), TARGET_PACKAGE + ".INTERNAL")


class UpdateMetadataTests(unittest.TestCase):
    def setUp(self):
        self.metadata = {
            "package": SOURCE_PACKAGE, "versionName": "V1.1.1", "versionCode": 111006,
            "url": "https://apppkg.fnnas.com/manager/android/example.apk", "md5": "a" * 32,
        }

    def test_接受原更新域名和官网音乐下载地址(self):
        validate_metadata(self.metadata)
        url = "https://iso.liveupdate.fnnas.com/x86_64/app/FN_Music_1.1.1_00611071528.apk"
        validate_metadata(dict(self.metadata, url=url))

    def test_非法字段仍被拒绝并指出字段名(self):
        for field, value in [
            ("url", "http://iso.liveupdate.fnnas.com/file.apk"),
            ("url", "https://iso.liveupdate.fnnas.com/file.zip"),
            ("url", "https://iso.liveupdate.fnnas.com.example.org/file.apk"),
            ("url", "https://[invalid"), ("url", None), ("package", "other"),
            ("versionCode", -1), ("versionCode", True), ("versionName", "1.1.0\ninvalid"),
            ("versionName", None), ("md5", "invalid"), ("md5", None),
        ]:
            with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, field):
                validate_metadata({**self.metadata, field: value})

    def test_域名错误只报告主机名(self):
        url = "https://user:private@example.org/private.apk?token=private"
        with self.assertRaisesRegex(ValueError, r"example\.org") as error:
            validate_metadata(dict(self.metadata, url=url))
        self.assertNotIn("private", str(error.exception))


if __name__ == "__main__":
    unittest.main()
