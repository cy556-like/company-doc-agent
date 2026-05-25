# DocAgent Android App (Capacitor)

将 DocAgent 网页应用打包为 Android APK 的 Capacitor 项目。

## 前提条件

1. **Node.js** >= 18.x
2. **Android Studio** (最新版)
3. **JDK** 17+
4. **Android SDK** (API 34+)

## 快速开始

### 1. 安装依赖

```bash
cd capacitor-app
npm install
```

### 2. 初始化 Capacitor（首次）

```bash
npx cap init DocAgent com.docagent.app --web-dir=../app/static
```

### 3. 添加 Android 平台

```bash
npx cap add android
```

### 4. 同步 Web 资源

```bash
npx cap sync
```

### 5. 在 Android Studio 中打开并运行

```bash
npx cap open android
```

在 Android Studio 中点击 Run 按钮即可在模拟器或真机上运行。

## 配置说明

### 连接后端服务器

在 `capacitor.config.json` 中的 `server.url` 配置后端地址：

- **本地开发（模拟器）**: `http://10.0.2.2:8000`
- **本地开发（真机）**: `http://你的电脑局域网IP:8000`
- **线上部署**: `https://your-domain.com`

⚠️ 如果使用线上URL，删除 `server.url` 和 `server.cleartext` 配置，
改为打包静态资源离线运行。

### 离线模式（可选）

如果想将所有资源打包进APK（不依赖服务器）：

1. 删除 `capacitor.config.json` 中的 `server.url` 字段
2. `webDir` 指向的目录会自动被打包进APK
3. API 请求仍需服务器运行（可配置为线上地址）

### 生成 Release APK

```bash
# 1. 同步最新代码
npx cap sync

# 2. 生成签名密钥（首次）
keytool -genkey -v -keystore docagent-release.keystore -alias docagent -keyalg RSA -keysize 2048 -validity 10000

# 3. 在 android/app/build.gradle 中配置签名

# 4. 构建 Release APK
cd android && ./gradlew assembleRelease

# 5. APK 输出位置
# android/app/build/outputs/apk/release/app-release.apk
```

## 文件结构

```
capacitor-app/
├── package.json              # Node.js 依赖配置
├── capacitor.config.json     # Capacitor 核心配置
├── android/                  # Android 原生项目（cap add 后生成）
│   ├── app/
│   │   ├── src/main/
│   │   │   ├── java/com/docagent/app/
│   │   │   ├── res/          # 图标、启动页等资源
│   │   │   └── AndroidManifest.xml
│   │   └── build.gradle
│   └── build.gradle
└── README.md
```

## 自定义

### 修改应用图标

1. 准备 1024x1024 的 PNG 图标
2. 使用 [Android Asset Studio](https://romannurik.github.io/AndroidAssetStudio/icons-launcher.html) 生成各尺寸图标
3. 替换 `android/app/src/main/res/mipmap-*` 目录下的图标文件

### 修改应用名称

编辑 `android/app/src/main/res/values/strings.xml`:
```xml
<string name="app_name">DocAgent</string>
<string name="title_activity_main">DocAgent</string>
```

### 修改启动页

编辑 `android/app/src/main/res/values/styles.xml` 和对应的 drawable 资源。
