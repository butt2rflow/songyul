package org.songyul.r10bridge;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

/**
 * Receives shots sent by the Garmin Golf app's E6 connection.
 * Protocol reference: r10_e6_server.py and THIRD_PARTY.md.
 * the app sends Handshake, Challenge, then per shot SetBallData, SetClubData, SendShot.
 * We ACK each; after a shot we send Disarm, ShotComplete, Arm; every 10 s a Ping once the last was answered.
 */
class E6Server {
    static final class Status {
        static final Status WAITING = new Status("e6Waiting", R.string.e6_waiting);
        static final Status ERROR = new Status("e6Error", R.string.e6_error);
        static final Status CONNECTED = new Status("garminConnected", R.string.garmin_connected);
        static final Status DISCONNECTED = new Status("garminDisconnected", R.string.garmin_disconnected);

        final String code;
        final int message;

        private Status(String code, int message) {
            this.code = code;
            this.message = message;
        }
    }

    interface Listener {
        void onStatus(Status status, String detail);
        void onShot(JSONObject shot);
        void onRaw(String direction, String message);
    }

    static final long ARM_EVERY_MS = 45000;   // re-send Arm after this long without one (keep-awake, see the pinger)

    private final int port;
    private final Listener listener;
    private volatile boolean running;
    private ServerSocket server;
    private int shotNo;

    E6Server(int port, Listener listener) {
        this.port = port;
        this.listener = listener;
    }

    void start() {
        running = true;
        new Thread(this::acceptLoop, "e6-accept").start();
    }

    synchronized int nextShot() { return ++shotNo; }

    // Open Garmin connections. stop() must close them too: closing only the listening socket left the Garmin app on the
    // old session after "수신 끄기 → 켜기", so shots were saved by the old service but never reached the page
    // (range 2026-11-15, 16:15-16:25). Closed, the app reconnects to the new receiver.
    private final List<Socket> sessions = new java.util.concurrent.CopyOnWriteArrayList<>();

    void stop() {
        running = false;
        try { if (server != null) server.close(); } catch (Exception ignored) { }
        for (Socket s : sessions) try { s.close(); } catch (Exception ignored) { }
        sessions.clear();
    }

    private void acceptLoop() {
        try {
            server = new ServerSocket();
            server.setReuseAddress(true);
            server.bind(new InetSocketAddress(port));
            listener.onStatus(Status.WAITING, Integer.toString(port));
            while (running) {
                Socket s = server.accept();
                sessions.add(s);
                new Thread(() -> { try { new Session(this, s).run(); } finally { sessions.remove(s); } }, "e6-session").start();
            }
        } catch (Exception e) {
            if (running) listener.onStatus(Status.ERROR, String.valueOf(e.getMessage()));
        }
    }

    /** Splits "{..}{..}" into whole JSON objects; returns the unconsumed tail in rest[0]. */
    static List<String> splitObjects(String text, String[] rest) {
        List<String> out = new ArrayList<>();
        int depth = 0, start = -1;
        boolean inStr = false, esc = false;
        int consumed = 0;
        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            if (inStr) {
                if (esc) esc = false;
                else if (c == '\\') esc = true;
                else if (c == '"') inStr = false;
                continue;
            }
            if (c == '"') inStr = true;
            else if (c == '{') { if (depth == 0) start = i; depth++; }
            else if (c == '}' && depth > 0) {
                depth--;
                if (depth == 0) { out.add(text.substring(start, i + 1)); consumed = i + 1; }
            }
        }
        rest[0] = text.substring(consumed);
        return out;
    }

    // Static (not inner) on purpose: JDK 21 javac writes an unnamed MethodParameters entry for inner-class
    // constructors, which crashes d8 from build-tools 34. The owner is passed in instead.
    private static class Session {
        private final E6Server owner;
        private final Listener listener;
        private final Socket sock;
        private OutputStream out;
        private volatile boolean gotPong;
        private volatile boolean open = true;
        private volatile boolean inShot;          // between SendShot and the Arm that ends it
        private volatile long lastArm;            // ms, last Arm we sent
        private JSONObject ball, club;

        Session(E6Server owner, Socket s) { this.owner = owner; this.listener = owner.listener; sock = s; }

        private synchronized void send(JSONObject o) {
            try {
                String m = o.toString();
                out.write(m.getBytes(StandardCharsets.UTF_8));
                out.flush();
                if ("Arm".equals(o.optString("SubType"))) lastArm = System.currentTimeMillis();
                listener.onRaw("→", m);
            } catch (Exception e) { open = false; }
        }

        private JSONObject obj(Object... kv) {
            JSONObject o = new JSONObject();
            try { for (int i = 0; i < kv.length; i += 2) o.put((String) kv[i], kv[i + 1]); }
            catch (JSONException ignored) { }
            return o;
        }

        private JSONObject ack(String sub) { return obj("Details", "Success.", "SubType", sub, "Type", "ACK"); }

        private JSONObject sim(String sub) { return obj("Type", "SimCommand", "SubType", sub); }

        void run() {
            String peer = String.valueOf(sock.getRemoteSocketAddress());
            listener.onStatus(Status.CONNECTED, peer);
            Thread pinger = new Thread(() -> {
                while (open) {
                    try { Thread.sleep(10000); } catch (InterruptedException e) { return; }
                    if (gotPong) { gotPong = false; send(sim("Ping")); }
                    // Keep the R10 awake. We only sent Arm at connect and after a shot, and the R10 idles after some
                    // minutes without a shot (range 2026-11-15: connected 16:03, two hits at 16:14 gave no shot, first
                    // shot 16:16:47). E6 Connect is seen re-waking an idle R10; re-sending Arm is our guess at
                    // what it does: check the R10's idle light / the raw log the next time it sits for 10+ min.
                    if (!inShot && System.currentTimeMillis() - lastArm > ARM_EVERY_MS) send(sim("Arm"));
                }
            }, "e6-ping");
            try {
                InputStream in = sock.getInputStream();
                out = sock.getOutputStream();
                pinger.start();
                byte[] buf = new byte[65536];
                String pending = "";
                int n;
                while (open && (n = in.read(buf)) > 0) {
                    String[] rest = new String[1];
                    List<String> msgs = splitObjects(pending + new String(buf, 0, n, StandardCharsets.UTF_8), rest);
                    pending = rest[0];
                    for (String m : msgs) handle(m);
                }
            } catch (Exception ignored) {
            } finally {
                open = false;
                pinger.interrupt();
                try { sock.close(); } catch (Exception ignored) { }
                if (owner.running) listener.onStatus(Status.DISCONNECTED, peer);
            }
        }

        private void handle(String raw) throws InterruptedException {
            listener.onRaw("←", raw);
            JSONObject m;
            try { m = new JSONObject(raw); } catch (JSONException e) { return; }
            String t = m.optString("Type");
            switch (t) {
                case "Handshake":
                    send(obj("Type", "Handshake", "Challenge", "", "E6Version", "",
                            "ProtocolVersion", "", "RequiredProtocolVersion", ""));
                    break;
                case "Challenge":
                    gotPong = true;
                    send(obj("Type", "Authentication", "Success", "true"));
                    send(sim("Arm"));  // tell the app we're ready for a shot (it showed a red "!" without this)
                    break;
                case "Pong":
                    gotPong = true;
                    break;
                case "SetBallData":
                    ball = m.optJSONObject("BallData");
                    send(ack("SetBallData"));
                    break;
                case "SetClubData":
                    club = m.optJSONObject("ClubData");
                    send(ack("SetClubData"));
                    break;
                case "SendShot": {
                    inShot = true;
                    long now = System.currentTimeMillis();
                    JSONObject shot = obj("shot", owner.nextShot(), "t_wall_ms", now,
                            "ball", ball == null ? JSONObject.NULL : ball,
                            "club", club == null ? JSONObject.NULL : club);
                    listener.onShot(shot);
                    send(ack("SendShot"));
                    send(sim("Disarm"));
                    Thread.sleep(500);
                    JSONObject done = sim("ShotComplete");
                    try {
                        done.put("Details", obj("BallData", ball == null ? JSONObject.NULL : ball,
                                "ClubData", club == null ? JSONObject.NULL : club,
                                "BallInHole", false, "BallLocation", "Fairway"));
                    } catch (JSONException ignored) { }
                    send(done);
                    ball = club = null;
                    Thread.sleep(500);
                    send(sim("Arm"));
                    inShot = false;
                    break;
                }
                case "SetClubType":
                    send(ack("SetClubType"));
                    send(sim("Arm"));
                    break;
                case "Disconnect":
                    open = false;
                    break;
                default:
                    send(ack(t.isEmpty() ? "Unknown" : t));
            }
        }
    }
}
