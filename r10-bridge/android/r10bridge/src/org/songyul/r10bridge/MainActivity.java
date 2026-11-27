package org.songyul.r10bridge;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.graphics.Typeface;
import android.os.Build;
import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/** One screen: start/stop, the address to type into the Garmin app, and the last shots/messages. */
public class MainActivity extends Activity implements BridgeService.Ui {
    private TextView info, state, log;
    private Button toggle;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        int pad = (int) (16 * getResources().getDisplayMetrics().density);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(pad, pad * 2, pad, pad);

        TextView title = new TextView(this);
        title.setText("R10 Bridge");
        title.setTextSize(26);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        root.addView(title);

        info = new TextView(this);
        info.setTextSize(15);
        info.setPadding(0, pad / 2, 0, pad / 2);
        root.addView(info);

        toggle = new Button(this);
        toggle.setTextSize(18);
        toggle.setOnClickListener(v -> {
            Intent i = new Intent(this, BridgeService.class);
            if (BridgeService.running) stopService(i);
            else startForegroundService(i);
            v.postDelayed(this::refresh, 300);
        });
        root.addView(toggle);

        Button page = new Button(this);
        page.setText("장갑 페이지 열기 (Chrome)");
        page.setOnClickListener(v -> {
            if (!BridgeService.running) startForegroundService(new Intent(this, BridgeService.class));
            // ?v=<install time>: Chrome reuses an open tab for the same URL without reloading it, so after an app update
            // the old page stayed on screen (2026-11-13). A new install time makes a new URL; the server ignores the query.
            long ver = 0;
            try { ver = getPackageManager().getPackageInfo(getPackageName(), 0).lastUpdateTime; } catch (Exception e) { }
            final String url = "http://127.0.0.1:" + BridgeService.WS_PORT + "/?v=" + ver;
            v.postDelayed(() -> startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url))), 400);
        });
        root.addView(page);

        state = new TextView(this);
        state.setTextSize(15);
        state.setPadding(0, pad / 2, 0, pad / 2);
        root.addView(state);

        ScrollView sv = new ScrollView(this);
        log = new TextView(this);
        log.setTextSize(12);
        log.setTypeface(Typeface.MONOSPACE);
        log.setTextIsSelectable(true);
        sv.addView(log);
        root.addView(sv, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f));
        setContentView(root);

        if (Build.VERSION.SDK_INT >= 33) requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, 1);
    }

    @Override protected void onResume() { super.onResume(); BridgeService.ui = this; refresh(); }

    @Override protected void onPause() { BridgeService.ui = null; super.onPause(); }

    static List<String> ipv4s() {
        List<String> out = new ArrayList<>();
        try {
            for (NetworkInterface ni : Collections.list(NetworkInterface.getNetworkInterfaces())) {
                if (!ni.isUp() || ni.isLoopback()) continue;
                for (InetAddress a : Collections.list(ni.getInetAddresses()))
                    if (a instanceof Inet4Address) out.add(a.getHostAddress() + " (" + ni.getName() + ")");
            }
        } catch (Exception ignored) { }
        return out;
    }

    @Override
    public void refresh() {
        StringBuilder sb = new StringBuilder("Garmin Golf 앱 → Manage Connection 에 입력:\n");
        sb.append("  Host  127.0.0.1   (이 폰에서 Garmin 앱을 쓸 때)\n");
        for (String ip : ipv4s()) sb.append("  Host  ").append(ip).append('\n');
        sb.append("  Port  ").append(BridgeService.E6_PORT).append("\n\n");
        sb.append("장갑 페이지: http://127.0.0.1:").append(BridgeService.WS_PORT).append("  (아래 버튼, 이 앱이 띄워 줘요)\n");
        sb.append("샷 파일: Download/R10Bridge/r10-shots-").append(ShotStore.today()).append(".jsonl");
        info.setText(sb.toString());
        toggle.setText(BridgeService.running ? "수신 끄기" : "수신 켜기");
        state.setText("상태: " + BridgeService.status + "   ·   샷 " + BridgeService.shots + "개");
        StringBuilder l = new StringBuilder();
        synchronized (BridgeService.lines) { for (String s : BridgeService.lines) l.append(s).append('\n'); }
        log.setText(l.length() == 0 ? "(아직 기록 없음)" : l.toString());
        log.setVisibility(View.VISIBLE);
    }
}
