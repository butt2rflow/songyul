package org.songyul.r10bridge;

import android.app.Activity;
import android.content.Context;
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
import java.util.function.Function;

/** One screen: start/stop, the address to type into the Garmin app, and the last shots/messages. */
public class MainActivity extends Activity implements BridgeService.Ui {
    private TextView info, state, log, languageLabel;
    private Button toggle, page, ko, en;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        int pad = (int) (16 * getResources().getDisplayMetrics().density);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(pad, pad * 2, pad, pad);

        TextView title = new TextView(this);
        title.setText(R.string.app_name);
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

        page = new Button(this);
        page.setOnClickListener(v -> {
            if (!BridgeService.running) startForegroundService(new Intent(this, BridgeService.class));
            // ?v=<install time>: Chrome reuses an open tab for the same URL without reloading it, so after an app update
            // the old page stayed on screen (2026-11-13). A new install time makes a new URL; the server ignores the query.
            long ver = 0;
            try { ver = getPackageManager().getPackageInfo(getPackageName(), 0).lastUpdateTime; } catch (Exception e) { }
            final String url = "http://127.0.0.1:" + BridgeService.WS_PORT + "/?v=" + ver + "&lang=" + BridgeStrings.language(this);
            v.postDelayed(() -> startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url))), 400);
        });
        root.addView(page);

        LinearLayout languages = new LinearLayout(this);
        languages.setGravity(android.view.Gravity.CENTER_VERTICAL);
        languageLabel = new TextView(this);
        ko = new Button(this);
        ko.setText(R.string.ko);
        ko.setOnClickListener(v -> setLanguage("ko"));
        en = new Button(this);
        en.setText(R.string.en);
        en.setOnClickListener(v -> setLanguage("en"));
        languages.addView(languageLabel);
        languages.addView(ko);
        languages.addView(en);
        root.addView(languages);

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

    private void setLanguage(String language) {
        BridgeStrings.saveLanguage(this, language);
        refresh();
        if (BridgeService.running) startService(new Intent(this, BridgeService.class).setAction(BridgeService.REFRESH_LANGUAGE));
    }

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
        Context c = BridgeStrings.localized(this);
        String language = BridgeStrings.language(this);
        languageLabel.setText(c.getString(R.string.language));
        ko.setEnabled(!language.equals("ko"));
        en.setEnabled(!language.equals("en"));
        page.setText(c.getString(R.string.open_page));
        StringBuilder sb = new StringBuilder(c.getString(R.string.guide)).append('\n');
        sb.append(c.getString(R.string.host_local)).append('\n');
        for (String ip : ipv4s()) sb.append("  Host  ").append(ip).append('\n');
        sb.append("  Port  ").append(BridgeService.E6_PORT).append("\n\n");
        sb.append(c.getString(R.string.page_address, BridgeService.WS_PORT)).append('\n');
        sb.append(c.getString(R.string.shot_file, ShotStore.today()));
        info.setText(sb.toString());
        toggle.setText(c.getString(BridgeService.running ? R.string.stop_receiver : R.string.start_receiver));
        state.setText(c.getString(R.string.state, BridgeService.status.apply(c), BridgeService.shots));
        StringBuilder l = new StringBuilder();
        synchronized (BridgeService.lines) {
            for (Function<Context, String> line : BridgeService.lines) l.append(line.apply(c)).append('\n');
        }
        log.setText(l.length() == 0 ? c.getString(R.string.no_log) : l.toString());
        log.setVisibility(View.VISIBLE);
    }
}
