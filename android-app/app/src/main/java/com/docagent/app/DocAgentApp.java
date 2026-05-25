package com.docagent.app;

import android.app.Application;
import android.webkit.WebView;

public class DocAgentApp extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        WebView.setWebContentsDebuggingEnabled(true);
    }
}
