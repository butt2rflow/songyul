package org.songyul.r10bridge;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;

import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.ArrayDeque;
import java.util.Date;
import java.util.Locale;

/** Foreground service: keeps the E6 receiver and the local WebSocket alive with the screen off. */
public class BridgeService extends Service implements E6Server.Listener {
    static final int E6_PORT = 2483;
    static final int WS_PORT = 8765;
    private static final String CH = "r10bridge";

    /** The activity registers here to get updates on the main thread. */
    interface Ui { void refresh(); }
    static volatile Ui ui;
    static volatile boolean running;
    static volatile String status = "꺼짐";
    static final ArrayDeque<String> lines = new ArrayDeque<>();  // newest first, for the screen
    static volatile int shots;

    private E6Server e6;
    private WsServer ws;
    private ShotStore store;
    private PowerManager.WakeLock wake;
    private final Handler main = new Handler(Looper.getMainLooper());

    static void addLine(String s) {
        synchronized (lines) {
            lines.addFirst(new SimpleDateFormat("HH:mm:ss", Locale.US).format(new Date()) + "  " + s);
            while (lines.size() > 60) lines.removeLast();
        }
    }

    private void poke() {
        main.post(() -> { Ui u = ui; if (u != null) u.refresh(); });
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (running) return START_STICKY;
        // When the phone is short of memory Android kills us and restarts the service from the background
        // (intent == null). Android 12+ forbids startForeground() there, and the restart crashed twice (range 2026-11-15
        // 16:42, ForegroundServiceStartNotAllowedException) with a crash dialog on top. Stop quietly until the user reopens the app
        // and taps 수신 켜기.
        try {
            startAsForeground();
        } catch (RuntimeException e) {
            addLine("백그라운드에서 다시 켤 수 없어요: 앱을 열고 수신 켜기를 눌러 주세요");
            status = "꺼짐 (휴대폰이 앱을 정리했어요)";
            poke();
            stopSelf();
            return START_NOT_STICKY;
        }
        running = true;
        store = new ShotStore(this);
        PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
        wake = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "r10bridge:recv");
        wake.acquire(6 * 60 * 60 * 1000L);  // a range session; the service stops it earlier

        ws = new WsServer(WS_PORT, getAssets());
        ws.start();
        e6 = new E6Server(E6_PORT, this);
        e6.start();
        return START_STICKY;
    }

    @Override public void onStatus(String text) {
        status = text;
        addLine(text);
        ws.broadcast("{\"type\":\"status\",\"text\":" + JSONObject.quote(text) + "}");
        poke();
    }

    @Override public void onShot(JSONObject shot) {
        shots++;
        store.appendShot(shot.toString());
        try {
            JSONObject msg = new JSONObject(shot.toString());
            msg.put("type", "shot");
            ws.broadcast(msg.toString());
        } catch (Exception ignored) { }
        addLine(describe(shot));
        poke();
    }

    @Override public void onRaw(String dir, String message) {
        store.appendRaw(System.currentTimeMillis() + " " + dir + " " + message);
        if (!message.contains("\"Ping\"") && !message.contains("\"Pong\"")) addLine(dir + " " + message);
        poke();
    }

    static double axis180(double a) { return a > 180 ? a - 360 : a; }   // R10 sends spin axis 0-360 (354 = -6)

    static String describe(JSONObject shot) {
        JSONObject b = shot.optJSONObject("ball"), c = shot.optJSONObject("club");
        if (b == null) b = new JSONObject();
        if (c == null) c = new JSONObject();
        return String.format(Locale.US, "샷 %d · 볼 %.1f mph · 방향 %+.1f° · 스핀축 %+.1f° · 클럽 %.1f · 패스 %+.1f° · 페이스 %+.1f°",
                shot.optInt("shot"), b.optDouble("BallSpeed", 0), b.optDouble("LaunchDirection", 0),
                axis180(b.optDouble("SpinAxis", 0)), c.optDouble("ClubHeadSpeed", 0),
                c.optDouble("ClubAnglePath", 0), c.optDouble("ClubAngleFace", 0));
    }

    private void startAsForeground() {
        NotificationManager nm = getSystemService(NotificationManager.class);
        nm.createNotificationChannel(new NotificationChannel(CH, "R10 수신", NotificationManager.IMPORTANCE_LOW));
        PendingIntent open = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class),
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        Notification n = new Notification.Builder(this, CH)
                .setContentTitle("R10 Bridge 켜짐")
                .setContentText("Garmin 앱 → 포트 " + E6_PORT + " · 장갑 페이지 → http://127.0.0.1:" + WS_PORT)
                .setSmallIcon(android.R.drawable.stat_sys_download_done)
                .setContentIntent(open)
                .setOngoing(true)
                .build();
        if (Build.VERSION.SDK_INT >= 29) startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
        else startForeground(1, n);
    }

    @Override
    public void onDestroy() {
        if (!running) { super.onDestroy(); return; }   // the start above was refused: nothing was opened
        running = false;
        if (e6 != null) e6.stop();
        if (ws != null) ws.stop();
        if (wake != null && wake.isHeld()) wake.release();
        status = "꺼짐";
        addLine("수신기 꺼짐");
        poke();
        super.onDestroy();
    }

    // No @Override: this callback is API 35 and we compile against android-34. Android 15+ caps dataSync at 6 h a day.
    public void onTimeout(int startId, int fgsType) {
        stopSelf();
    }

    @Override
    public IBinder onBind(Intent intent) { return null; }
}
