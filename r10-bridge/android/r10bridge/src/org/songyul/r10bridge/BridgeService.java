package org.songyul.r10bridge;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
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
import java.util.function.Function;

/** Foreground service: keeps the E6 receiver and the local WebSocket alive with the screen off. */
public class BridgeService extends Service implements E6Server.Listener {
    static final int E6_PORT = 2483;
    static final int WS_PORT = 8765;
    static final String REFRESH_LANGUAGE = "org.songyul.r10bridge.REFRESH_LANGUAGE";
    private static final String CH = "r10bridge";

    /** The activity registers here to get updates on the main thread. */
    interface Ui { void refresh(); }
    static volatile Ui ui;
    static volatile boolean running;
    static volatile Function<Context, String> status = c -> c.getString(R.string.status_off);
    static final ArrayDeque<Function<Context, String>> lines = new ArrayDeque<>();  // newest first
    static volatile int shots;

    private E6Server e6;
    private WsServer ws;
    private ShotStore store;
    private PowerManager.WakeLock wake;
    private final Handler main = new Handler(Looper.getMainLooper());

    private static void addLine(Function<Context, String> message) {
        String time = new SimpleDateFormat("HH:mm:ss", Locale.US).format(new Date());
        synchronized (lines) {
            lines.addFirst(c -> time + "  " + message.apply(c));
            while (lines.size() > 60) lines.removeLast();
        }
    }

    private void poke() {
        main.post(() -> { Ui u = ui; if (u != null) u.refresh(); });
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && REFRESH_LANGUAGE.equals(intent.getAction())) {
            if (!running) {
                stopSelf(startId);
                return START_NOT_STICKY;
            }
            getSystemService(NotificationManager.class).notify(1, notification());
            return START_STICKY;
        }
        if (running) return START_STICKY;
        // When the phone is short of memory Android kills us and restarts the service from the background
        // (intent == null). Android 12+ forbids startForeground() there, and the restart crashed twice (range 2026-11-15
        // 16:42, ForegroundServiceStartNotAllowedException) with a crash dialog on top. Stop quietly until the user reopens the app
        // and starts the receiver.
        try {
            startAsForeground();
        } catch (RuntimeException e) {
            addLine(c -> c.getString(R.string.background_failed));
            status = c -> c.getString(R.string.status_background_off);
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

    @Override public void onStatus(E6Server.Status state, String detail) {
        if (!running) return;
        Function<Context, String> message = c -> c.getString(state.message, detail);
        status = message;
        addLine(message);
        ws.broadcast("{\"type\":\"status\",\"code\":" + JSONObject.quote(state.code) + ",\"detail\":" + JSONObject.quote(detail)
                + ",\"text\":" + JSONObject.quote(message.apply(BridgeStrings.localized(this))) + "}");
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
        addLine(c -> describe(c, shot));
        poke();
    }

    @Override public void onRaw(String dir, String message) {
        store.appendRaw(System.currentTimeMillis() + " " + dir + " " + message);
        if (!message.contains("\"Ping\"") && !message.contains("\"Pong\"")) addLine(c -> dir + " " + message);
        poke();
    }

    static double axis180(double a) { return a > 180 ? a - 360 : a; }   // R10 sends spin axis 0-360 (354 = -6)

    private static String describe(Context context, JSONObject shot) {
        JSONObject b = shot.optJSONObject("ball"), c = shot.optJSONObject("club");
        if (b == null) b = new JSONObject();
        if (c == null) c = new JSONObject();
        return context.getString(R.string.shot_description,
                shot.optInt("shot"), b.optDouble("BallSpeed", 0), b.optDouble("LaunchDirection", 0),
                axis180(b.optDouble("SpinAxis", 0)), c.optDouble("ClubHeadSpeed", 0),
                c.optDouble("ClubAnglePath", 0), c.optDouble("ClubAngleFace", 0));
    }

    private Notification notification() {
        Context c = BridgeStrings.localized(this);
        NotificationManager nm = getSystemService(NotificationManager.class);
        nm.createNotificationChannel(new NotificationChannel(CH, c.getString(R.string.notification_channel), NotificationManager.IMPORTANCE_LOW));
        PendingIntent open = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class),
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        return new Notification.Builder(this, CH)
                .setContentTitle(c.getString(R.string.notification_title))
                .setContentText(c.getString(R.string.notification_body, E6_PORT, WS_PORT))
                .setSmallIcon(android.R.drawable.stat_sys_download_done)
                .setContentIntent(open)
                .setOngoing(true)
                .build();
    }

    private void startAsForeground() {
        Notification n = notification();
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
        status = c -> c.getString(R.string.status_off);
        addLine(c -> c.getString(R.string.receiver_off));
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
