package com.tabdeck.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.ApplicationInfo;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.media.AudioAttributes;
import android.media.AudioFormat;
import android.media.AudioTrack;
import android.net.DhcpInfo;
import android.net.wifi.WifiManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.io.BufferedInputStream;
import java.io.InputStream;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicBoolean;

public class MainActivity extends Activity {

    private static final String PREFS = "tabdeck_prefs";
    private static final String KEY_WIFI_HOST = "wifi_host";
    private static final String KEY_KEEP_AWAKE = "keep_awake";
    private static final String KEY_INTRO_DONE = "intro_done_v1";
    private static final String DEFAULT_WIFI_HOST = "";
    private static final String USB_URL = "http://127.0.0.1:8765";
    private static final int DISCOVERY_PORT = 8766;

    private WebView webView;
    private LinearLayout offlineOverlay;
    private TextView offlineStatus;
    private FrameLayout introOverlay;
    private TextView introStepBadge;
    private TextView introTitle;
    private TextView introBody;
    private Button introBackBtn;
    private Button introNextBtn;
    private TextView debugBadge;
    private boolean isDebugBuild = false;
    private int introStep = 0;

    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final AtomicBoolean connecting = new AtomicBoolean(false);
    private volatile boolean isActivityActive = false;
    private volatile boolean isConnected = false;

    private boolean keepAwake = true;
    private boolean dimmed = false;
    private boolean immersive = true;
    private boolean videoFullscreen = false;
    private String currentUrl = USB_URL;
    private long lastBackPress = 0L;

    // Live PC -> Tablet Audio Stream state
    private volatile boolean audioStreaming = false;
    private Thread audioThread = null;
    private volatile HttpURLConnection activeAudioConn = null;

    private final Runnable autoRetryRunnable = new Runnable() {
        @Override
        public void run() {
            if (isActivityActive && !isConnected) {
                probeAndConnect(false, false, false, false);
                mainHandler.postDelayed(this, 2500);
            }
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        SharedPreferences prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        keepAwake = prefs.getBoolean(KEY_KEEP_AWAKE, true);
        isDebugBuild = (getApplicationInfo().flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0;
        WebView.setWebContentsDebuggingEnabled(isDebugBuild);
        applyKeepAwake();

        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.parseColor("#090C13"));

        webView = new WebView(this);
        webView.setBackgroundColor(Color.parseColor("#090C13"));
        WebSettings ws = webView.getSettings();
        ws.setJavaScriptEnabled(true);
        ws.setDomStorageEnabled(true);
        ws.setDatabaseEnabled(true);
        ws.setCacheMode(WebSettings.LOAD_NO_CACHE);
        ws.setMediaPlaybackRequiresUserGesture(false);
        ws.setUseWideViewPort(true);
        ws.setLoadWithOverviewMode(true);

        webView.addJavascriptInterface(new NativeBridge(), "TabDeckNative");
        webView.setWebChromeClient(new WebChromeClient());
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                if (url != null && url.startsWith("http")) {
                    isConnected = true;
                    mainHandler.removeCallbacks(autoRetryRunnable);
                    offlineOverlay.setVisibility(View.GONE);
                    webView.setVisibility(View.VISIBLE);
                }
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest req, WebResourceError err) {
                super.onReceivedError(view, req, err);
                if (req != null && req.isForMainFrame()) {
                    isConnected = false;
                    showOffline("Searching for your laptop via USB and Wi-Fi...\n(Auto-connects as soon as laptop is ready)");
                    scheduleAutoRetry();
                }
            }
        });

        root.addView(webView, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        offlineOverlay = buildOfflineOverlay();
        root.addView(offlineOverlay, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        introOverlay = buildIntroOverlay();
        introOverlay.setVisibility(View.GONE);
        root.addView(introOverlay, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        if (isDebugBuild) {
            debugBadge = new TextView(this);
            debugBadge.setText("DEBUG · Idle");
            debugBadge.setTextSize(10);
            debugBadge.setTextColor(Color.parseColor("#FEF08A"));
            debugBadge.setBackgroundColor(Color.parseColor("#AA1E293B"));
            debugBadge.setPadding(dp(8), dp(3), dp(8), dp(3));
            FrameLayout.LayoutParams dbp = new FrameLayout.LayoutParams(
                    ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT,
                    Gravity.BOTTOM | Gravity.END);
            dbp.setMargins(0, 0, dp(8), dp(8));
            root.addView(debugBadge, dbp);
        }

        setContentView(root);
        root.post(this::applyImmersive);

        if (!prefs.getBoolean(KEY_INTRO_DONE, false)) {
            showIntroOverlay();
        }
        probeAndConnect(true, false, false, false);
    }

    @Override
    protected void onStart() {
        super.onStart();
        isActivityActive = true;
    }

    @Override
    protected void onResume() {
        super.onResume();
        isActivityActive = true;
        if (!isConnected) {
            probeAndConnect(false, false, false, false);
            scheduleAutoRetry();
        }
    }

    @Override
    protected void onPause() {
        isActivityActive = false;
        mainHandler.removeCallbacks(autoRetryRunnable);
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        mainHandler.removeCallbacks(autoRetryRunnable);
        stopAudioStream();
        super.onDestroy();
    }

    private void scheduleAutoRetry() {
        mainHandler.removeCallbacks(autoRetryRunnable);
        mainHandler.postDelayed(autoRetryRunnable, 2500);
    }

    // -----------------------------------------------------------------------
    // Seamless Zero-Config Auto-Discovery: USB -> Saved Wi-Fi -> UDP Broadcast
    // -----------------------------------------------------------------------
    private void probeAndConnect(boolean showSpinner, boolean resumeAudio, boolean resumeVideo, boolean resumeFull) {
        if (!connecting.compareAndSet(false, true)) return;
        if (showSpinner) {
            showOffline("Connecting to your laptop (USB or Wi-Fi)...");
        }

        final String savedWifi = getSharedPreferences(PREFS, MODE_PRIVATE)
                .getString(KEY_WIFI_HOST, DEFAULT_WIFI_HOST);

        new Thread(() -> {
            try {
                if (canReach("127.0.0.1", 8765, 350)) {
                    connectToBase(USB_URL, "USB", resumeAudio, resumeVideo, resumeFull);
                    return;
                }

                String host = savedWifi;
                int port = 8765;
                if (savedWifi.contains(":")) {
                    String[] parts = savedWifi.split(":");
                    host = parts[0];
                    try { port = Integer.parseInt(parts[1]); } catch (Exception ignored) {}
                }
                if (!host.isEmpty() && canReach(host, port, 700)) {
                    connectToBase("http://" + host + ":" + port, "Wi-Fi", resumeAudio, resumeVideo, resumeFull);
                    return;
                }

                String discovered = discoverPcOverUdp();
                if (discovered != null && !discovered.isEmpty()) {
                    String dHost = discovered.split(":")[0];
                    int dPort = 8765;
                    if (discovered.contains(":")) {
                        try { dPort = Integer.parseInt(discovered.split(":")[1]); } catch (Exception ignored) {}
                    }
                    if (canReach(dHost, dPort, 800)) {
                        getSharedPreferences(PREFS, MODE_PRIVATE).edit()
                                .putString(KEY_WIFI_HOST, dHost + ":" + dPort).apply();
                        connectToBase("http://" + dHost + ":" + dPort, "Wi-Fi", resumeAudio, resumeVideo, resumeFull);
                        return;
                    }
                }

                isConnected = false;
                showOffline("Waiting for laptop...\nPlug in USB or connect to the same Wi-Fi.\n(Auto-retrying every 2s)");
                scheduleAutoRetry();
            } finally {
                connecting.set(false);
            }
        }, "tabdeck-connect").start();
    }

    private void connectToBase(String baseUrl, String modeLabel, boolean resumeAudio, boolean resumeVideo, boolean resumeFull) {
        boolean wasAudio = audioStreaming || resumeAudio;
        if (!baseUrl.equals(currentUrl)) {
            stopAudioStream();
        }
        currentUrl = baseUrl;
        isConnected = true;
        mainHandler.removeCallbacks(autoRetryRunnable);

        StringBuilder q = new StringBuilder();
        if (resumeVideo) q.append(q.length() == 0 ? "?" : "&").append("video=1");
        if (resumeFull) q.append(q.length() == 0 ? "?" : "&").append("full=1");
        if (wasAudio) q.append(q.length() == 0 ? "?" : "&").append("audio=1");
        final String target = baseUrl + "/" + q;

        runOnUiThread(() -> {
            offlineOverlay.setVisibility(View.GONE);
            webView.setVisibility(View.VISIBLE);
            webView.loadUrl(target);
            if (debugBadge != null) {
                debugBadge.setText("DEBUG · " + modeLabel + " (" + baseUrl.replace("http://", "") + ")");
            }
            Toast.makeText(MainActivity.this, "Connected via " + modeLabel, Toast.LENGTH_SHORT).show();
        });
    }

    private String discoverPcOverUdp() {
        WifiManager.MulticastLock mlock = null;
        DatagramSocket sock = null;
        try {
            WifiManager wm = (WifiManager) getApplicationContext().getSystemService(Context.WIFI_SERVICE);
            if (wm != null) {
                mlock = wm.createMulticastLock("tabdeck_disc");
                mlock.setReferenceCounted(false);
                mlock.acquire();
            }
            sock = new DatagramSocket();
            sock.setBroadcast(true);
            sock.setSoTimeout(900);

            byte[] probe = "TABDECK_DISCOVER".getBytes(StandardCharsets.UTF_8);
            try {
                sock.send(new DatagramPacket(probe, probe.length, InetAddress.getByName("255.255.255.255"), DISCOVERY_PORT));
            } catch (Exception ignored) {}

            if (wm != null) {
                try {
                    DhcpInfo dhcp = wm.getDhcpInfo();
                    if (dhcp != null && dhcp.ipAddress != 0 && dhcp.netmask != 0) {
                        int bcast = (dhcp.ipAddress & dhcp.netmask) | ~dhcp.netmask;
                        byte[] quads = new byte[4];
                        for (int k = 0; k < 4; k++) quads[k] = (byte) ((bcast >> (k * 8)) & 0xFF);
                        sock.send(new DatagramPacket(probe, probe.length, InetAddress.getByAddress(quads), DISCOVERY_PORT));
                    }
                } catch (Exception ignored) {}
            }

            byte[] buf = new byte[512];
            DatagramPacket pkt = new DatagramPacket(buf, buf.length);
            sock.receive(pkt);
            String msg = new String(pkt.getData(), 0, pkt.getLength(), StandardCharsets.UTF_8).trim();
            if (msg.startsWith("TABDECK:")) {
                String[] parts = msg.split(":");
                String port = parts.length > 1 ? parts[1] : "8765";
                String ip = (parts.length > 2 && !parts[2].isEmpty() && !parts[2].startsWith("127."))
                        ? parts[2]
                        : pkt.getAddress().getHostAddress();
                return ip + ":" + port;
            }
        } catch (Exception ignored) {
        } finally {
            if (sock != null) try { sock.close(); } catch (Exception ignored) {}
            if (mlock != null && mlock.isHeld()) try { mlock.release(); } catch (Exception ignored) {}
        }
        return null;
    }

    private boolean canReach(String host, int port, int timeoutMs) {
        try (Socket s = new Socket()) {
            s.connect(new InetSocketAddress(host, port), timeoutMs);
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    // -----------------------------------------------------------------------
    // Live PC -> Tablet Audio Streaming (Frame-Aligned Low-Latency AudioTrack)
    // -----------------------------------------------------------------------
    private boolean startAudioStream() {
        if (audioStreaming) return true;
        audioStreaming = true;
        final String streamUrl = currentUrl + "/api/audio/stream";

        audioThread = new Thread(() -> {
            AudioTrack track = null;
            HttpURLConnection conn = null;
            try {
                URL u = new URL(streamUrl);
                conn = (HttpURLConnection) u.openConnection();
                conn.setConnectTimeout(3000);
                conn.setReadTimeout(5000);
                conn.connect();
                activeAudioConn = conn;

                int rate = 48000;
                int channels = 2;
                try {
                    String rHdr = conn.getHeaderField("X-Sample-Rate");
                    if (rHdr != null) rate = Integer.parseInt(rHdr.trim());
                    String cHdr = conn.getHeaderField("X-Channels");
                    if (cHdr != null) channels = Integer.parseInt(cHdr.trim());
                } catch (Exception ignored) {}

                int channelMask = (channels == 1)
                        ? AudioFormat.CHANNEL_OUT_MONO
                        : AudioFormat.CHANNEL_OUT_STEREO;
                int frameBytes = channels * 2;
                int minBuf = AudioTrack.getMinBufferSize(rate, channelMask, AudioFormat.ENCODING_PCM_16BIT);
                int bufSize = Math.max(minBuf * 3, frameBytes * 3840);

                AudioTrack.Builder builder = new AudioTrack.Builder()
                        .setAudioAttributes(new AudioAttributes.Builder()
                                .setUsage(AudioAttributes.USAGE_MEDIA)
                                .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                                .build())
                        .setAudioFormat(new AudioFormat.Builder()
                                .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                                .setSampleRate(rate)
                                .setChannelMask(channelMask)
                                .build())
                        .setBufferSizeInBytes(bufSize)
                        .setTransferMode(AudioTrack.MODE_STREAM);
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    builder.setPerformanceMode(AudioTrack.PERFORMANCE_MODE_LOW_LATENCY);
                }
                track = builder.build();

                InputStream in = new BufferedInputStream(conn.getInputStream(), 16384);
                byte[] buf = new byte[3840];
                int carry = 0;
                int prefilled = 0;
                int prefillTarget = frameBytes * 1920;
                boolean started = false;
                while (audioStreaming) {
                    int n = in.read(buf, carry, buf.length - carry);
                    if (n < 0) break;
                    int total = carry + n;
                    int aligned = total - (total % frameBytes);
                    if (aligned > 0) {
                        track.write(buf, 0, aligned, AudioTrack.WRITE_BLOCKING);
                        if (!started) {
                            prefilled += aligned;
                            if (prefilled >= prefillTarget) {
                                track.play();
                                started = true;
                            }
                        }
                    }
                    carry = total - aligned;
                    if (carry > 0) {
                        System.arraycopy(buf, aligned, buf, 0, carry);
                    }
                }
            } catch (Exception ignored) {
            } finally {
                audioStreaming = false;
                activeAudioConn = null;
                if (track != null) {
                    try { track.stop(); } catch (Exception ignored) {}
                    try { track.release(); } catch (Exception ignored) {}
                }
                if (conn != null) {
                    try { conn.disconnect(); } catch (Exception ignored) {}
                }
                runOnUiThread(() -> {
                    if (webView != null) {
                        webView.evaluateJavascript("window.onNativeAudioState && window.onNativeAudioState(false);", null);
                    }
                });
            }
        }, "tabdeck-pcm-player");
        audioThread.start();
        return true;
    }

    private void stopAudioStream() {
        audioStreaming = false;
        HttpURLConnection conn = activeAudioConn;
        if (conn != null) {
            new Thread(() -> {
                try { conn.disconnect(); } catch (Exception ignored) {}
            }).start();
        }
        if (audioThread != null) {
            audioThread.interrupt();
            audioThread = null;
        }
    }

    private LinearLayout buildOfflineOverlay() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setGravity(Gravity.CENTER);
        box.setBackgroundColor(Color.parseColor("#090C13"));
        int pad = dp(32);
        box.setPadding(pad, pad, pad, pad);

        TextView title = new TextView(this);
        title.setText("TabDeck");
        title.setTextSize(32);
        title.setTextColor(Color.parseColor("#F1F5F9"));
        title.setGravity(Gravity.CENTER);
        box.addView(title);

        offlineStatus = new TextView(this);
        offlineStatus.setText("Connecting to your laptop...");
        offlineStatus.setTextSize(15);
        offlineStatus.setTextColor(Color.parseColor("#94A3B8"));
        offlineStatus.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams sp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        sp.topMargin = dp(12);
        sp.bottomMargin = dp(24);
        box.addView(offlineStatus, sp);

        LinearLayout btnRow = new LinearLayout(this);
        boolean isNarrow = getResources().getDisplayMetrics().widthPixels < dp(500);
        btnRow.setOrientation(isNarrow ? LinearLayout.VERTICAL : LinearLayout.HORIZONTAL);
        btnRow.setGravity(Gravity.CENTER);

        Button retryBtn = new Button(this);
        retryBtn.setText("Retry Now");
        retryBtn.setAllCaps(false);
        retryBtn.setTextColor(Color.WHITE);
        retryBtn.setBackgroundColor(Color.parseColor("#0284C7"));
        retryBtn.setPadding(dp(24), dp(12), dp(24), dp(12));
        retryBtn.setOnClickListener(v -> probeAndConnect(true, false, false, false));

        Button cfgBtn = new Button(this);
        cfgBtn.setText("PC Server IP");
        cfgBtn.setAllCaps(false);
        cfgBtn.setTextColor(Color.parseColor("#E2E8F0"));
        cfgBtn.setBackgroundColor(Color.parseColor("#1E293B"));
        cfgBtn.setPadding(dp(20), dp(12), dp(20), dp(12));
        cfgBtn.setOnClickListener(v -> showServerDialog());

        Button guideBtn = new Button(this);
        guideBtn.setText("? Guide");
        guideBtn.setAllCaps(false);
        guideBtn.setTextColor(Color.parseColor("#7DD3FC"));
        guideBtn.setBackgroundColor(Color.parseColor("#0F172A"));
        guideBtn.setPadding(dp(18), dp(12), dp(18), dp(12));
        guideBtn.setOnClickListener(v -> showIntroOverlay());

        LinearLayout.LayoutParams bp = new LinearLayout.LayoutParams(
                isNarrow ? dp(220) : ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        if (isNarrow) bp.bottomMargin = dp(10);
        else bp.rightMargin = dp(12);
        btnRow.addView(retryBtn, bp);
        btnRow.addView(cfgBtn, bp);
        LinearLayout.LayoutParams lastBp = new LinearLayout.LayoutParams(
                isNarrow ? dp(220) : ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        btnRow.addView(guideBtn, lastBp);

        box.addView(btnRow);
        return box;
    }

    private FrameLayout buildIntroOverlay() {
        FrameLayout backdrop = new FrameLayout(this);
        backdrop.setBackgroundColor(Color.parseColor("#EC070B14"));
        backdrop.setClickable(true);

        int screenW = getResources().getDisplayMetrics().widthPixels;
        boolean compact = screenW < dp(500);

        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(false);

        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        int pad = dp(compact ? 18 : 26);
        card.setPadding(pad, pad, pad, pad);
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(Color.parseColor("#111827"));
        bg.setCornerRadius(dp(18));
        bg.setStroke(dp(1), Color.parseColor("#38BDF8"));
        card.setBackground(bg);

        introStepBadge = new TextView(this);
        introStepBadge.setTextSize(11);
        introStepBadge.setTypeface(Typeface.DEFAULT_BOLD);
        introStepBadge.setTextColor(Color.parseColor("#38BDF8"));
        card.addView(introStepBadge);

        introTitle = new TextView(this);
        introTitle.setTextSize(compact ? 20 : 24);
        introTitle.setTypeface(Typeface.DEFAULT_BOLD);
        introTitle.setTextColor(Color.parseColor("#F8FAFC"));
        LinearLayout.LayoutParams tp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        tp.topMargin = dp(6);
        card.addView(introTitle, tp);

        introBody = new TextView(this);
        introBody.setTextSize(compact ? 13.5f : 15f);
        introBody.setLineSpacing(dp(4), 1.0f);
        introBody.setTextColor(Color.parseColor("#CBD5E1"));
        LinearLayout.LayoutParams bodyLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        bodyLp.topMargin = dp(12);
        bodyLp.bottomMargin = dp(18);
        card.addView(introBody, bodyLp);

        LinearLayout nav = new LinearLayout(this);
        nav.setOrientation(LinearLayout.HORIZONTAL);
        nav.setGravity(Gravity.END | Gravity.CENTER_VERTICAL);

        Button skipBtn = new Button(this);
        skipBtn.setText("Skip");
        skipBtn.setAllCaps(false);
        skipBtn.setTextColor(Color.parseColor("#94A3B8"));
        skipBtn.setBackgroundColor(Color.TRANSPARENT);
        skipBtn.setMinimumWidth(0);
        skipBtn.setPadding(dp(10), dp(8), dp(10), dp(8));
        skipBtn.setOnClickListener(v -> finishIntro());

        introBackBtn = new Button(this);
        introBackBtn.setText("Back");
        introBackBtn.setAllCaps(false);
        introBackBtn.setTextColor(Color.parseColor("#E2E8F0"));
        introBackBtn.setBackgroundColor(Color.parseColor("#1E293B"));
        introBackBtn.setMinimumWidth(0);
        introBackBtn.setPadding(dp(14), dp(8), dp(14), dp(8));
        introBackBtn.setOnClickListener(v -> {
            if (introStep > 0) { introStep--; renderIntroStep(); }
        });

        introNextBtn = new Button(this);
        introNextBtn.setText("Next");
        introNextBtn.setAllCaps(false);
        introNextBtn.setTextColor(Color.WHITE);
        introNextBtn.setBackgroundColor(Color.parseColor("#0284C7"));
        introNextBtn.setMinimumWidth(0);
        introNextBtn.setPadding(dp(16), dp(8), dp(16), dp(8));
        introNextBtn.setOnClickListener(v -> {
            if (introStep < 2) { introStep++; renderIntroStep(); }
            else finishIntro();
        });

        LinearLayout.LayoutParams navSpace = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        navSpace.rightMargin = dp(8);
        nav.addView(skipBtn, navSpace);
        nav.addView(introBackBtn, navSpace);
        nav.addView(introNextBtn);
        card.addView(nav);

        scroll.addView(card, new ScrollView.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        int cardWidth = Math.min(dp(520), Math.max(dp(280), screenW - dp(28)));
        FrameLayout.LayoutParams cardLp = new FrameLayout.LayoutParams(
                cardWidth, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.CENTER);
        cardLp.setMargins(dp(14), dp(16), dp(14), dp(16));
        backdrop.addView(scroll, cardLp);
        return backdrop;
    }

    private void renderIntroStep() {
        final String[] titles = {
            "Welcome to TabDeck" + (isDebugBuild ? " (Debug)" : ""),
            "Zero-Config 2-Step Setup",
            "Quick Tips & Shortcuts"
        };
        final String[] bodies = {
            "Turn your Android tablet into an all-in-one Windows companion:\n\n"
                + "• Stream Deck-style customizable PC macropad\n"
                + "• Live per-app Windows audio mixer & low-latency wireless speaker\n"
                + "• Fullscreen touchscreen, native Windows Ink S-Pen & 3rd extended screen\n"
                + "• Multi Control: share your laptop mouse & keyboard with tablets and unrooted phones",
            "1. On Windows: double-click TabDeck.exe (it installs dependencies automatically on first launch and sits quietly in your System Tray).\n\n"
                + "2. Connect your tablet via USB cable OR join the same Wi-Fi network.\n\n"
                + "TabDeck discovers your laptop automatically — no manual IP setup needed! (Right-click the tray icon -> Enable Wi-Fi Access if Windows Firewall blocks Wi-Fi.)",
            "• Fullscreen Menu: long-press the corner toolbar to drag it anywhere on screen.\n"
                + "• Type into PC: tap the Keyboard button in fullscreen to type with Samsung Keyboard or S-Pen handwriting.\n"
                + "• 3rd Screen & Auto-Quality: tap 3rd Scr to extend Windows, and let Auto-Adaptive Quality boost sharpness on Netflix/YouTube and FPS on drawing apps.\n"
                + "• Multi Control: tap Devices to drag & drop your tablet/phone around your monitors, or press Ctrl+Alt+M on your laptop."
        };
        introStepBadge.setText("STEP " + (introStep + 1) + " OF 3");
        introTitle.setText(titles[introStep]);
        introBody.setText(bodies[introStep]);
        introBackBtn.setVisibility(introStep == 0 ? View.GONE : View.VISIBLE);
        introNextBtn.setText(introStep == 2 ? "Start Using TabDeck" : "Next");
    }

    private void showIntroOverlay() {
        runOnUiThread(() -> {
            introStep = 0;
            renderIntroStep();
            introOverlay.setVisibility(View.VISIBLE);
        });
    }

    private void finishIntro() {
        getSharedPreferences(PREFS, MODE_PRIVATE).edit().putBoolean(KEY_INTRO_DONE, true).apply();
        runOnUiThread(() -> introOverlay.setVisibility(View.GONE));
    }

    private void showOffline(String msg) {
        runOnUiThread(() -> {
            offlineStatus.setText(msg);
            offlineOverlay.setVisibility(View.VISIBLE);
        });
    }

    private void showServerDialog() {
        runOnUiThread(() -> {
            SharedPreferences prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
            String cur = prefs.getString(KEY_WIFI_HOST, DEFAULT_WIFI_HOST);

            EditText input = new EditText(this);
            input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
            input.setText(cur);
            input.setHint("192.168.1.100:8765");
            int pad = dp(18);
            input.setPadding(pad, pad, pad, pad);

            new AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog_Alert)
                    .setTitle("PC Wi-Fi Server Address")
                    .setMessage("TabDeck auto-discovers USB & Wi-Fi automatically. You can also set a manual IP:Port here:")
                    .setView(input)
                    .setPositiveButton("Save & Connect", (d, w) -> {
                        String val = input.getText().toString().trim()
                                .replace("http://", "").replace("https://", "");
                        if (!val.isEmpty()) {
                            if (!val.contains(":")) val = val + ":8765";
                            prefs.edit().putString(KEY_WIFI_HOST, val).apply();
                        }
                        probeAndConnect(true, false, false, false);
                    })
                    .setNegativeButton("Cancel", null)
                    .show();
        });
    }

    private void applyKeepAwake() {
        runOnUiThread(() -> {
            if (keepAwake) getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            else getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        });
    }

    private void applyBrightness() {
        runOnUiThread(() -> {
            WindowManager.LayoutParams lp = getWindow().getAttributes();
            lp.screenBrightness = dimmed ? 0.04f : WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_NONE;
            getWindow().setAttributes(lp);
        });
    }

    private void applyImmersive() {
        runOnUiThread(() -> {
            try {
                if (getWindow() == null || getWindow().peekDecorView() == null) return;
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                    WindowInsetsController c = getWindow().getInsetsController();
                    if (c != null) {
                        if (immersive) {
                            c.hide(WindowInsets.Type.statusBars() | WindowInsets.Type.navigationBars());
                            c.setSystemBarsBehavior(WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
                        } else {
                            c.show(WindowInsets.Type.statusBars() | WindowInsets.Type.navigationBars());
                        }
                    }
                } else {
                    View decor = getWindow().getDecorView();
                    if (immersive) {
                        decor.setSystemUiVisibility(
                                View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                                        | View.SYSTEM_UI_FLAG_FULLSCREEN
                                        | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                                        | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                                        | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                                        | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION);
                    } else {
                        decor.setSystemUiVisibility(View.SYSTEM_UI_FLAG_VISIBLE);
                    }
                }
            } catch (Exception ignored) {}
        });
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus && immersive) applyImmersive();
    }

    @Override
    public void onBackPressed() {
        if (videoFullscreen) {
            videoFullscreen = false;
            runOnUiThread(() -> {
                if (webView != null) {
                    webView.evaluateJavascript("window.exitVideoFullscreen && window.exitVideoFullscreen();", null);
                }
            });
            return;
        }
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
            return;
        }
        long now = System.currentTimeMillis();
        if (now - lastBackPress < 1800) {
            super.onBackPressed();
        } else {
            lastBackPress = now;
            Toast.makeText(this, "Press back again to exit TabDeck", Toast.LENGTH_SHORT).show();
        }
    }

    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }

    private class NativeBridge {
        @JavascriptInterface
        public boolean isNativeApp() { return true; }

        @JavascriptInterface
        public boolean isConnectedViaUsb() { return currentUrl.startsWith("http://127.0.0.1"); }

        @JavascriptInterface
        public boolean isKeepScreenOn() { return keepAwake; }

        @JavascriptInterface
        public boolean toggleKeepScreenOn() {
            keepAwake = !keepAwake;
            getSharedPreferences(PREFS, MODE_PRIVATE).edit().putBoolean(KEY_KEEP_AWAKE, keepAwake).apply();
            applyKeepAwake();
            return keepAwake;
        }

        @JavascriptInterface
        public boolean toggleDim() {
            dimmed = !dimmed;
            applyBrightness();
            return dimmed;
        }

        @JavascriptInterface
        public boolean toggleImmersive() {
            immersive = !immersive;
            applyImmersive();
            return immersive;
        }

        @JavascriptInterface
        public boolean isPcAudioStreaming() { return audioStreaming; }

        @JavascriptInterface
        public boolean togglePcAudioStream() {
            if (audioStreaming) {
                stopAudioStream();
                return false;
            } else {
                return startAudioStream();
            }
        }

        @JavascriptInterface
        public boolean startPcAudioStream() { return startAudioStream(); }

        @JavascriptInterface
        public void setVideoFullscreen(boolean fs) { videoFullscreen = fs; }

        @JavascriptInterface
        public void failoverReconnect(boolean resumeAudio, boolean resumeVideo, boolean resumeFull) {
            isConnected = false;
            probeAndConnect(false, resumeAudio, resumeVideo, resumeFull);
        }

        @JavascriptInterface
        public void openServerSettings() { showServerDialog(); }

        @JavascriptInterface
        public void showIntro() { showIntroOverlay(); }

        @JavascriptInterface
        public boolean isDebugBuild() { return isDebugBuild; }

        @JavascriptInterface
        public void reconnect() { probeAndConnect(true, false, false, false); }
    }
}
