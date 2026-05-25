# DocAgent ProGuard Rules
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}
-keep class com.docagent.app.** { *; }
