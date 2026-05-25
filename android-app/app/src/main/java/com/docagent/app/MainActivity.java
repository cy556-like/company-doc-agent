package com.docagent.app;

import android.annotation.SuppressLint;
import android.annotation.TargetApi;
import android.app.Activity;
import android.app.AlertDialog;
import android.app.DownloadManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.net.ConnectivityManager;
import android.net.NetworkInfo;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.text.TextUtils;
import android.util.Log;
import android.view.KeyEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.webkit.ConsoleMessage;
import android.webkit.CookieManager;
import android.webkit.DownloadListener;
import android.webkit.GeolocationPermissions;
import android.webkit.JsResult;
import android.webkit.MimeTypeMap;
import android.webkit.PermissionRequest;
import android.webkit.SslErrorHandler;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

/**
 * DocAgent Android 主界面
 *
 * 技术方案：原生 Android WebView（与豆包、Kimi等AI App同方案）
 * - WebView 全屏加载 Web 应用
 * - 原生启动画面
 * - 服务器地址动态配置
 * - 文件上传/下载支持
 * - SSE流式响应支持
 * - 返回键导航
 */
public class MainActivity extends Activity {

    private static final String TAG = "DocAgent";
    private static final String PREFS_NAME = "docagent_prefs";
    private static final String KEY_SERVER_URL = "server_url";
    private static final String KEY_FIRST_LAUNCH = "first_launch";
    private static final String DEFAULT_URL = "";  // 首次启动由用户输入公网地址，如 http://123.45.67.89:8000

    private WebView webView;
    private ProgressBar progressBar;
    private FrameLayout splashScreen;
    private LinearLayout errorScreen;
    private EditText serverInput;
    private SharedPreferences prefs;

    // File upload support (Android 5.0+)
    private ValueCallback<Uri[]> filePathCallback;
    private static final int FILE_CHOOSER_REQUEST = 10001;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);

        // Build UI
        createUI();

        // Setup WebView
        setupWebView();

        // Auto connect
        String serverUrl = prefs.getString(KEY_SERVER_URL, "");
        if (TextUtils.isEmpty(serverUrl)) {
            // First launch - show config
            showConfigScreen();
        } else {
            connectToServer(serverUrl);
        }
    }

    /**
     * 创建完整UI布局（纯代码，仿豆包风格）
     */
    private void createUI() {
        // Root frame layout
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.parseColor("#F8F7F3"));

        // === WebView Container ===
        FrameLayout webContainer = new FrameLayout(this);
        webView = new WebView(this);
        webContainer.addView(webView, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT));

        // Progress bar at top
        progressBar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progressBar.setMax(100);
        progressBar.setProgress(0);
        progressBar.setBackgroundColor(Color.parseColor("#E0DFD6"));
        FrameLayout.LayoutParams pbParams = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT, 6);
        webContainer.addView(progressBar, pbParams);

        root.addView(webContainer, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT));

        // === Splash Screen ===
        splashScreen = new FrameLayout(this);
        splashScreen.setBackgroundColor(Color.parseColor("#F8F7F3"));

        LinearLayout splashContent = new LinearLayout(this);
        splashContent.setOrientation(LinearLayout.VERTICAL);
        splashContent.setGravity(android.view.Gravity.CENTER);

        // Logo
        View logoCircle = new View(this);
        logoCircle.setBackgroundColor(Color.parseColor("#1A1A2E"));
        LinearLayout.LayoutParams logoParams = new LinearLayout.LayoutParams(120, 120);
        logoParams.bottomMargin = 24;
        // Use rounded shape
        logoCircle.setBackgroundResource(android.R.drawable.dialog_holo_dark_frame);
        splashContent.addView(logoCircle, logoParams);

        // Logo text "D"
        TextView logoText = new TextView(this);
        logoText.setText("D");
        logoText.setTextSize(48);
        logoText.setTextColor(Color.parseColor("#1A1A2E"));
        logoText.setTypeface(null, android.graphics.Typeface.BOLD);
        logoText.setGravity(android.view.Gravity.CENTER);
        LinearLayout.LayoutParams ltParams = new LinearLayout.LayoutParams(120, 120);
        ltParams.bottomMargin = 32;
        // We'll use a FrameLayout to overlay text on circle
        FrameLayout logoFrame = new FrameLayout(this);
        View circleBg = new View(this);
        circleBg.setBackgroundColor(Color.parseColor("#1A1A2E"));
        logoFrame.addView(circleBg, new FrameLayout.LayoutParams(120, 120));
        logoFrame.addView(logoText, new FrameLayout.LayoutParams(120, 120));

        splashContent.removeView(logoCircle);
        splashContent.addView(logoFrame, ltParams);

        // Title
        TextView titleText = new TextView(this);
        titleText.setText("DocAgent");
        titleText.setTextSize(24);
        titleText.setTextColor(Color.parseColor("#1A1A2E"));
        titleText.setTypeface(null, android.graphics.Typeface.BOLD);
        titleText.setGravity(android.view.Gravity.CENTER);
        LinearLayout.LayoutParams tParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
        tParams.bottomMargin = 8;
        splashContent.addView(titleText, tParams);

        // Subtitle
        TextView subText = new TextView(this);
        subText.setText("企业文档智能体");
        subText.setTextSize(14);
        subText.setTextColor(Color.parseColor("#656565"));
        subText.setGravity(android.view.Gravity.CENTER);
        LinearLayout.LayoutParams sParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
        sParams.bottomMargin = 32;
        splashContent.addView(subText, sParams);

        // Status
        TextView statusText = new TextView(this);
        statusText.setText("连接服务器中...");
        statusText.setTextSize(13);
        statusText.setTextColor(Color.parseColor("#999999"));
        statusText.setGravity(android.view.Gravity.CENTER);
        statusText.setId(View.generateViewId());
        splashContent.addView(statusText, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT));

        splashScreen.addView(splashContent, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT));

        root.addView(splashScreen, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT));

        // === Error/Config Screen ===
        errorScreen = new LinearLayout(this);
        errorScreen.setOrientation(LinearLayout.VERTICAL);
        errorScreen.setGravity(android.view.Gravity.CENTER);
        errorScreen.setBackgroundColor(Color.parseColor("#F8F7F3"));
        errorScreen.setVisibility(View.GONE);
        errorScreen.setPadding(48, 0, 48, 0);

        // Error icon
        TextView errIcon = new TextView(this);
        errIcon.setText("⚠");
        errIcon.setTextSize(48);
        errIcon.setGravity(android.view.Gravity.CENTER);
        errorScreen.addView(errIcon, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT));

        // Error title
        TextView errTitle = new TextView(this);
        errTitle.setText("无法连接服务器");
        errTitle.setTextSize(18);
        errTitle.setTextColor(Color.parseColor("#1A1A2E"));
        errTitle.setTypeface(null, android.graphics.Typeface.BOLD);
        errTitle.setGravity(android.view.Gravity.CENTER);
        LinearLayout.LayoutParams etParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
        etParams.topMargin = 16;
        etParams.bottomMargin = 8;
        errorScreen.addView(errTitle, etParams);

        // Error message
        TextView errMsg = new TextView(this);
        errMsg.setText("请输入 DocAgent 服务器地址后重试");
        errMsg.setTextSize(14);
        errMsg.setTextColor(Color.parseColor("#656565"));
        errMsg.setGravity(android.view.Gravity.CENTER);
        errMsg.setId(View.generateViewId());
        LinearLayout.LayoutParams emParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
        emParams.bottomMargin = 24;
        errorScreen.addView(errMsg, emParams);

        // Server input
        serverInput = new EditText(this);
        serverInput.setHint("http://你的公网IP:8000");
        serverInput.setPadding(24, 16, 24, 16);
        serverInput.setBackgroundColor(Color.parseColor("#FFFFFF"));
        serverInput.setTextColor(Color.parseColor("#1A1A2E"));
        serverInput.setTextSize(14);
        serverInput.setSingleLine(true);
        serverInput.setInputType(android.text.InputType.TYPE_TEXT_VARIATION_URI);
        LinearLayout.LayoutParams siParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
        siParams.bottomMargin = 16;
        errorScreen.addView(serverInput, siParams);

        // Connect button
        LinearLayout btnRow = new LinearLayout(this);
        btnRow.setOrientation(LinearLayout.HORIZONTAL);
        btnRow.setGravity(android.view.Gravity.CENTER);

        TextView connectBtn = new TextView(this);
        connectBtn.setText("  连接服务器  ");
        connectBtn.setTextSize(15);
        connectBtn.setTextColor(Color.WHITE);
        connectBtn.setBackgroundColor(Color.parseColor("#1A1A2E"));
        connectBtn.setPadding(48, 16, 48, 16);
        connectBtn.setOnClickListener(v -> {
            String url = serverInput.getText().toString().trim();
            if (!url.isEmpty()) {
                if (!url.startsWith("http")) url = "http://" + url;
                prefs.edit().putString(KEY_SERVER_URL, url).apply();
                connectToServer(url);
            } else {
                Toast.makeText(this, "请输入服务器地址", Toast.LENGTH_SHORT).show();
            }
        });

        TextView resetBtn = new TextView(this);
        resetBtn.setText("  重置  ");
        resetBtn.setTextSize(15);
        resetBtn.setTextColor(Color.parseColor("#1A1A2E"));
        resetBtn.setBackgroundColor(Color.parseColor("#E0DFD6"));
        resetBtn.setPadding(32, 16, 32, 16);
        resetBtn.setOnClickListener(v -> serverInput.setText(""));

        btnRow.addView(connectBtn);
        btnRow.addView(resetBtn, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT));
        errorScreen.addView(btnRow, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT));

        // Hint
        TextView hint = new TextView(this);
        hint.setText("提示：请输入服务器的公网IP地址\n格式：http://公网IP:8000\n例如：http://123.45.67.89:8000");
        hint.setTextSize(12);
        hint.setTextColor(Color.parseColor("#999999"));
        hint.setGravity(android.view.Gravity.CENTER);
        LinearLayout.LayoutParams hParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
        hParams.topMargin = 16;
        errorScreen.addView(hint, hParams);

        root.addView(errorScreen, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT));

        setContentView(root);
    }

    private void showConfigScreen() {
        splashScreen.setVisibility(View.GONE);
        errorScreen.setVisibility(View.VISIBLE);
        serverInput.setText(DEFAULT_URL);
    }

    /**
     * 配置 WebView（豆包等AI App的核心方案）
     */
    @SuppressLint("SetJavaScriptEnabled")
    private void setupWebView() {
        WebSettings s = webView.getSettings();

        // JavaScript - 必须开启
        s.setJavaScriptEnabled(true);

        // 存储 - 支持localStorage/sessionStorage
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);

        // 文件访问
        s.setAllowFileAccess(true);
        s.setAllowContentAccess(true);

        // 视口 - 自适应屏幕
        s.setUseWideViewPort(true);
        s.setLoadWithOverviewMode(true);
        s.setLayoutAlgorithm(WebSettings.LayoutAlgorithm.TEXT_AUTOSIZING);

        // 缓存 - 优先网络，离线时用缓存
        s.setCacheMode(WebSettings.LOAD_DEFAULT);

        // 允许混合内容（HTTP+HTTPS）
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        }

        // 文字缩放
        s.setTextZoom(100);

        // 支持缩放
        s.setSupportZoom(false);
        s.setBuiltInZoomControls(false);

        // 自动加载图片
        s.setLoadsImagesAutomatically(true);
        s.setBlockNetworkImage(false);

        // Cookie
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true);

        // WebViewClient
        webView.setWebViewClient(new DocAgentWebViewClient());

        // WebChromeClient
        webView.setWebChromeClient(new DocAgentChromeClient());

        // Download support
        webView.setDownloadListener((url, userAgent, contentDisposition, mimetype, contentLength) -> {
            try {
                DownloadManager.Request request = new DownloadManager.Request(Uri.parse(url));
                request.setMimeType(mimetype);
                String fileName = URLUtil.guessFileName(url, contentDisposition, mimetype);
                request.setTitle(fileName);
                request.setDescription("正在下载...");
                request.allowScanningByMediaScanner();
                request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
                request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, fileName);
                DownloadManager dm = (DownloadManager) getSystemService(DOWNLOAD_SERVICE);
                dm.enqueue(request);
                Toast.makeText(this, "开始下载: " + fileName, Toast.LENGTH_SHORT).show();
            } catch (Exception e) {
                // Fallback: open in browser
                Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
                startActivity(intent);
            }
        });
    }

    private void connectToServer(String url) {
        splashScreen.setVisibility(View.VISIBLE);
        errorScreen.setVisibility(View.GONE);
        webView.loadUrl(url);

        // Timeout
        new Handler(Looper.getMainLooper()).postDelayed(() -> {
            if (splashScreen.getVisibility() == View.VISIBLE) {
                showConfigScreen();
                serverInput.setText(url);
            }
        }, 15000);
    }

    /**
     * WebViewClient - 处理页面加载
     */
    private class DocAgentWebViewClient extends WebViewClient {
        @Override
        public void onPageStarted(WebView view, String url, Bitmap favicon) {
            super.onPageStarted(view, url, favicon);
            progressBar.setProgress(0);
            progressBar.setVisibility(View.VISIBLE);
        }

        @Override
        public void onPageFinished(WebView view, String url) {
            super.onPageFinished(view, url);
            progressBar.setVisibility(View.GONE);

            if (splashScreen.getVisibility() == View.VISIBLE) {
                splashScreen.animate()
                        .alpha(0f)
                        .setDuration(400)
                        .withEndAction(() -> splashScreen.setVisibility(View.GONE))
                        .start();
            }
        }

        @Override
        public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
            super.onReceivedError(view, request, error);
            if (request.isForMainFrame()) {
                showConfigScreen();
                serverInput.setText(prefs.getString(KEY_SERVER_URL, DEFAULT_URL));
            }
        }

        @Override
        public void onReceivedSslError(WebView view, SslErrorHandler handler, android.net.http.SslError error) {
            // 开发/内网环境允许自签名证书
            AlertDialog.Builder builder = new AlertDialog.Builder(MainActivity.this);
            builder.setMessage("SSL证书不受信任，是否继续？")
                    .setPositiveButton("继续", (d, w) -> handler.proceed())
                    .setNegativeButton("取消", (d, w) -> handler.cancel())
                    .setOnCancelListener(d -> handler.cancel())
                    .show();
        }

        @Override
        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            String url = request.getUrl().toString();
            String serverUrl = prefs.getString(KEY_SERVER_URL, DEFAULT_URL);
            if (url.startsWith(serverUrl) || url.startsWith("file:///")) {
                return false;
            }
            // External links open in browser
            try {
                Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
                startActivity(intent);
            } catch (Exception e) {
                Log.w(TAG, "Cannot open URL: " + url, e);
            }
            return true;
        }
    }

    /**
     * WebChromeClient - 处理进度、文件上传、对话框
     */
    private class DocAgentChromeClient extends WebChromeClient {
        @Override
        public void onProgressChanged(WebView view, int newProgress) {
            if (newProgress == 100) {
                progressBar.setVisibility(View.GONE);
            } else {
                progressBar.setProgress(newProgress);
            }
        }

        @Override
        public boolean onJsAlert(WebView view, String url, String message, JsResult result) {
            new AlertDialog.Builder(MainActivity.this)
                    .setMessage(message)
                    .setPositiveButton("确定", (d, w) -> result.confirm())
                    .setOnCancelListener(d -> result.cancel())
                    .show();
            return true;
        }

        @Override
        public boolean onJsConfirm(WebView view, String url, String message, JsResult result) {
            new AlertDialog.Builder(MainActivity.this)
                    .setMessage(message)
                    .setPositiveButton("确定", (d, w) -> result.confirm())
                    .setNegativeButton("取消", (d, w) -> result.cancel())
                    .setOnCancelListener(d -> result.cancel())
                    .show();
            return true;
        }

        @Override
        public boolean onShowFileChooser(WebView webView, ValueCallback<Uri[]> filePathCb, FileChooserParams params) {
            filePathCallback = filePathCb;
            try {
                Intent intent = params.createIntent();
                startActivityForResult(intent, FILE_CHOOSER_REQUEST);
            } catch (Exception e) {
                filePathCallback = null;
                return false;
            }
            return true;
        }

        @Override
        public void onGeolocationPermissionsShowPrompt(String origin, GeolocationPermissions.Callback callback) {
            callback.invoke(origin, true, false);
        }

        @Override
        public void onPermissionRequest(PermissionRequest request) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                request.grant(request.getResources());
            }
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == FILE_CHOOSER_REQUEST && filePathCallback != null) {
            Uri[] results = null;
            if (resultCode == RESULT_OK && data != null) {
                if (data.getData() != null) {
                    results = new Uri[]{data.getData()};
                } else if (data.getClipData() != null) {
                    results = new Uri[data.getClipData().getItemCount()];
                    for (int i = 0; i < data.getClipData().getItemCount(); i++) {
                        results[i] = data.getClipData().getItemAt(i).getUri();
                    }
                }
            }
            filePathCallback.onReceiveValue(results);
            filePathCallback = null;
        }
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_BACK && webView.canGoBack()) {
            webView.goBack();
            return true;
        }
        return super.onKeyDown(keyCode, event);
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (webView != null) webView.onResume();
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (webView != null) webView.onPause();
    }

    @Override
    protected void onDestroy() {
        if (webView != null) {
            ((ViewGroup) webView.getParent()).removeView(webView);
            webView.destroy();
            webView = null;
        }
        super.onDestroy();
    }
}
