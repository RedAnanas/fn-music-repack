# 飞牛音乐自动改包

每 6 小时查询飞牛官方音乐 Android 更新服务，发现新版本后下载官方 APK，核验官方签名和文件哈希，修改包名并使用固定证书签名，随后发布到 GitHub Releases。

| 项目 | 配置 |
|---|---|
| 原始包名 | `com.trim.music` |
| 发布包名 | `com.hunantv.imgo.activity` |
| 安装名称 | 飞牛音乐 |
| Android 版本 | 保留上游 `versionName` 和 `versionCode` |
| Release 标签 | `v版本号-versionCode`，例如 `v1.1.0-110024` |
| 安装包 | 每个 Release 一个 APK，包含原包提供的 ARM64 和 ARM32 库 |

## 通过 KomiStore 更新

在 KomiStore 中打开本仓库，首次从 Releases 下载并安装 APK，让商店关联仓库和应用。后续版本保持相同包名和签名证书，可通过 KomiStore 检查更新。

首次安装要求设备上没有其他使用 `com.hunantv.imgo.activity` 且签名不同的应用。

## 自动构建

工作流支持定时执行和手动执行。进入 Actions，选择“检查更新并发布 APK”，点击“Run workflow”即可检查一次。

源码中的测试会核对包名、权限、Provider 和程序类名的处理边界。构建时还会核对官方 APK 证书、MD5、版本、成品证书、ZIP 对齐、程序代码与资源一致性，以及清单解码结果。全部检查成功后才公开 Release，失败时已有正式版本继续保留。若官方更新接口将 MD5 留空，则必须用固定的官方证书通过 APK v2 或 v3 内容签名验证；接口或下载响应中提供的 MD5 不匹配时仍会拒绝发布。`build.json` 记录实际下载原包的 SHA-256。

GitHub 的定时执行可能延迟，公开仓库连续 60 天无活动时定时工作流会被停用，可在 Actions 中重新启用。

## GitHub Secrets

| 名称 | 用途 |
|---|---|
| `UPDATE_API_KEY` | 官方音乐客户端的更新请求参数 |
| `UPDATE_SIGN_PREFIX` | 更新请求签名参数 |
| `KEYSTORE_B64` | 固定自签名 JKS 的 Base64 编码 |
| `KEYSTORE_PASSWORD` | JKS 和私钥密码 |

签名别名为 `repackage`。证书指纹固定在构建脚本中，后续发布应继续使用同一份 JKS。请独立备份该证书和密码。

当前流程通过静态构建检查，手机上的登录、播放、后台行为及 KomiStore 覆盖升级需要在实际设备上验证。
