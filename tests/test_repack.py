"""核对改包边界与更新元数据校验。"""

import copy
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

    def test_拒绝错误下载域名和非法版本(self):
        metadata = {
            "package": SOURCE_PACKAGE, "versionName": "V1.1.0", "versionCode": 110024,
            "url": "https://apppkg.fnnas.com/manager/android/example.apk", "md5": "a" * 32,
        }
        validate_metadata(metadata)
        for key, value in [("url", "https://example.com/file.apk"), ("versionCode", -1), ("versionName", "1.1.0\ninvalid")]:
            with self.subTest(field=key):
                invalid = copy.deepcopy(metadata)
                invalid[key] = value
                with self.assertRaises(ValueError):
                    validate_metadata(invalid)


if __name__ == "__main__":
    unittest.main()
