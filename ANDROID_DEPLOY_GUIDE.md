# DocAgent 安卓应用打包指南

本文档介绍将 DocAgent 网页应用打包为安卓应用的三种方案。

---

## 方案对比

| 特性 | PWA | Capacitor | 原生 WebView |
|------|-----|-----------|-------------|
| **难度** | ⭐ 最简单 | ⭐⭐ 中等 | ⭐⭐⭐ 较复杂 |
| **产出** | 浏览器添加到桌面 | 真实 APK | 真实 APK |
| **上架商店** | 不能 | 可以 | 可以 |
| **原生功能** | 有限 | 丰富（插件） | 完全控制 |
| **需 Node.js** | 否 | 是 | 否 |
| **需 Android Studio** | 否 | 是 | 是 |
| **离线运行** | 部分 | 可配置 | 可配置 |
| **推荐场景** | 快速体验 | 正式发布 | 深度定制 |

---

## 方案一：PWA（推荐快速体验）

### 原理
在现有网页上添加 `manifest.json` + `service-worker.js`，用户通过浏览器"添加到主屏幕"即可获得类似原生App的体验。

### 已完成的修改
- ✅ `app/static/manifest.json` — PWA配置文件
- ✅ `app/static/sw.js` — Service Worker（离线缓存）
- ✅ `app/static/icons/` — 多尺寸图标（72~512px）
- ✅ `app/static/index.html` — 添加了manifest链接、SW注册、安装按钮

### 使用方式

1. 启动后端服务：
```bash
cd C:\company-doc-agent
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

2. 在手机浏览器访问：`http://你的电脑IP:8000`

3. **Chrome 浏览器**：点击菜单 → "添加到主屏幕"
   **华为浏览器**：点击菜单 → "添加到桌面"
   **Safari (iOS)**：点击分享 → "添加到主屏幕"

4. 从桌面图标打开，即可全屏运行，类似原生App

### 注意事项
- 手机和电脑必须在同一局域网
- 需要 HTTPS 才能触发自动安装提示（局域网HTTP可手动添加）
- 后端服务必须持续运行

---

## 方案二：Capacitor（推荐正式发布）

### 原理
使用 Capacitor 框架将 Web 应用包装为原生 Android 项目，生成可安装的 APK。

### 前提条件
- Node.js >= 18.x
- Android Studio (最新版)
- JDK 17+

### 步骤

```bash
# 1. 进入 Capacitor 项目目录
cd capacitor-app

# 2. 安装依赖
npm install

# 3. 初始化 Capacitor（首次）
npx cap init DocAgent com.docagent.app --web-dir=../app/static

# 4. 添加 Android 平台（首次）
npx cap add android

# 5. 同步 Web 资源（每次修改前端后执行）
npx cap sync

# 6. 在 Android Studio 中打开
npx cap open android

# 7. 在 Android Studio 中点击 Run 按钮运行
```

### 配置服务器地址

编辑 `capacitor-app/capacitor.config.json`:

```json
{
    "server": {
        "url": "http://你的服务器地址:8000",
        "cleartext": true
    }
}
```

- **模拟器**: `http://10.0.2.2:8000`
- **真机（局域网）**: `http://192.168.x.x:8000`
- **线上服务器**: `https://your-domain.com`（删除 `cleartext` 字段）

### 生成 Release APK

```bash
# 同步最新代码
npx cap sync

# 生成签名密钥（首次）
keytool -genkey -v -keystore docagent.keystore -alias docagent -keyalg RSA -keysize 2048 -validity 10000

# 构建发布版
cd android && ./gradlew assembleRelease

# APK 输出位置
# android/app/build/outputs/apk/release/app-release.apk
```

---

## 方案三：原生 Android WebView（推荐深度定制）

### 原理
纯 Java 编写原生 Android 应用，使用 WebView 组件加载 DocAgent 网页。

### 特点
- 无需 Node.js 和 Capacitor
- 完全控制原生行为
- 支持服务器地址配置界面
- 支持文件上传、返回键导航、进度条

### 步骤

1. 用 **Android Studio** 打开 `android-app` 目录

2. 同步 Gradle（Android Studio 自动提示）

3. 连接手机或启动模拟器

4. 点击 **Run** 按钮运行

5. 首次启动需输入服务器地址

### 修改默认服务器

编辑 `android-app/app/src/main/java/com/docagent/app/MainActivity.java`:

```java
private static final String DEFAULT_URL = "http://你的服务器地址:8000";
```

### 生成 APK

```bash
cd android-app

# Debug 版
./gradlew assembleDebug
# 输出: app/build/outputs/apk/debug/app-debug.apk

# Release 版
./gradlew assembleRelease
# 输出: app/build/outputs/apk/release/app-release.apk
```

---

## 部署架构

```
┌─────────────────────┐     HTTP/HTTPS     ┌─────────────────────┐
│   Android 设备       │ ────────────────── │  服务器 (ECS)        │
│                     │                    │                     │
│  ┌───────────────┐  │                    │  ┌───────────────┐  │
│  │ DocAgent App  │  │     API 请求       │  │ FastAPI 后端   │  │
│  │ (WebView)     │──┼───────────────────▶│  │ :8000         │  │
│  │               │◀─┼───── SSE 流式 ─────│  │               │  │
│  └───────────────┘  │                    │  └───────┬───────┘  │
│                     │                    │          │          │
│  方案1: PWA         │                    │  ┌───────▼───────┐  │
│  方案2: Capacitor   │                    │  │ ChromaDB      │  │
│  方案3: 原生WebView │                    │  │ 知识库向量存储  │  │
│                     │                    │  └───────┬───────┘  │
└─────────────────────┘                    │          │          │
                                           │  ┌───────▼───────┐  │
                                           │  │ 智谱GLM API   │  │
                                           │  │ 大语言模型服务  │  │
                                           │  └───────────────┘  │
                                           └─────────────────────┘
```

---

## 常见问题

### Q: 真机无法连接服务器？
A: 确保手机和电脑在同一局域网，且电脑防火墙放行了 8000 端口。
```bash
# 查看 Windows 局域网IP
ipconfig

# 防火墙放行 8000 端口
netsh advfirewall firewall add rule name="DocAgent" dir=in action=allow protocol=TCP localport=8000
```

### Q: 上架 Google Play / 华为应用商店？
A: 使用方案二或方案三生成签名 APK/AAB，然后在开发者后台提交。
- Google Play 需要 AAB 格式：`./gradlew bundleRelease`
- 华为应用商店接受 APK 格式

### Q: 如何实现离线运行？
A: 当前架构依赖后端服务，无法完全离线。如需离线，需要：
1. 将 AI 推理部署在设备端（如 ONNX Runtime）
2. 或使用本地小型模型（如 MobileLLM）

### Q: Capacitor 和原生 WebView 怎么选？
A:
- 需要快速开发、跨平台（iOS+Android）→ 选 Capacitor
- 只需 Android、需要深度定制原生行为 → 选原生 WebView
- 两个方案生成的 APK 用户体验基本一致

---

## 文件清单

```
company-doc-agent/
├── app/static/
│   ├── manifest.json                    # [PWA] 应用清单
│   ├── sw.js                            # [PWA] Service Worker
│   ├── icons/                           # [PWA] 图标 (72~512px)
│   │   ├── icon-72.png
│   │   ├── icon-96.png
│   │   ├── ...
│   │   └── icon-512.png
│   └── index.html                       # [已修改] 添加PWA支持
│
├── capacitor-app/                       # [方案二] Capacitor 项目
│   ├── package.json                     # Node.js 依赖
│   ├── capacitor.config.json            # Capacitor 配置
│   ├── www/index.html                   # 启动/配置页面
│   └── README.md                        # Capacitor 使用说明
│
└── android-app/                         # [方案三] 原生 Android 项目
    ├── app/
    │   ├── build.gradle                 # App 模块构建
    │   ├── proguard-rules.pro           # 混淆规则
    │   └── src/main/
    │       ├── AndroidManifest.xml      # 清单文件
    │       ├── java/com/docagent/app/
    │       │   └── MainActivity.java    # 主界面
    │       └── res/                     # 资源文件
    ├── build.gradle                     # 项目构建
    ├── settings.gradle                  # 项目设置
    └── README.md                        # Android 使用说明
```
