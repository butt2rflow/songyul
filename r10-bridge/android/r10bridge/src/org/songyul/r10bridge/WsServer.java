package org.songyul.r10bridge;

import android.content.res.AssetManager;
import android.util.Base64;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

/**
 * Tiny HTTP + WebSocket server on 127.0.0.1. Plain GETs serve the glove page bundled in the APK (assets/web/),
 * and a WebSocket upgrade on the same port gets each shot live. Serving the page from the same loopback origin is
 * what keeps Chrome's local-network rules out of the way.
 * Server → page only: text frames with JSON ({"type":"shot",...} or {"type":"status",...}).
 * Bound to loopback, so nothing outside the phone can connect.
 */
class WsServer {
    private static final String GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
    private final int port;
    private final List<OutputStream> clients = new CopyOnWriteArrayList<>();
    private volatile boolean running;
    private ServerSocket server;

    private final AssetManager assets;

    WsServer(int port, AssetManager assets) { this.port = port; this.assets = assets; }

    int clientCount() { return clients.size(); }

    void start() {
        running = true;
        new Thread(() -> {
            try {
                server = new ServerSocket();
                server.setReuseAddress(true);
                // Explicit IPv4: on Android getLoopbackAddress() is ::1, and Chrome's 127.0.0.1 was refused.
                server.bind(new InetSocketAddress(InetAddress.getByName("127.0.0.1"), port));
                while (running) {
                    Socket s = server.accept();
                    new Thread(() -> handshake(s), "ws-client").start();
                }
            } catch (Exception ignored) { }
        }, "ws-accept").start();
    }

    void stop() {
        running = false;
        try { if (server != null) server.close(); } catch (Exception ignored) { }
        for (OutputStream o : clients) try { o.close(); } catch (Exception ignored) { }
        clients.clear();
    }

    private void handshake(Socket s) {
        OutputStream out = null;
        try {
            InputStream in = s.getInputStream();
            StringBuilder head = new StringBuilder();
            int c;
            while ((c = in.read()) != -1) {
                head.append((char) c);
                if (head.length() > 8192) throw new Exception("header too long");
                if (head.length() >= 4 && head.substring(head.length() - 4).equals("\r\n\r\n")) break;
            }
            String key = null;
            for (String line : head.toString().split("\r\n")) {
                int i = line.indexOf(':');
                if (i > 0 && line.substring(0, i).trim().equalsIgnoreCase("Sec-WebSocket-Key")) key = line.substring(i + 1).trim();
            }
            if (key == null) { serveFile(s, head.toString()); return; }
            byte[] sha = MessageDigest.getInstance("SHA-1").digest((key + GUID).getBytes(StandardCharsets.US_ASCII));
            String accept = Base64.encodeToString(sha, Base64.NO_WRAP);
            out = s.getOutputStream();
            out.write(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                    + "Sec-WebSocket-Accept: " + accept + "\r\n\r\n").getBytes(StandardCharsets.US_ASCII));
            out.flush();
            clients.add(out);
            // Drain whatever the page sends (pings, close) until it goes away.
            byte[] buf = new byte[1024];
            while (in.read(buf) != -1) { }
        } catch (Exception ignored) {
        } finally {
            if (out != null) clients.remove(out);
            try { s.close(); } catch (Exception ignored) { }
        }
    }

    private void serveFile(Socket s, String head) throws Exception {
        String[] req = head.split("\r\n", 2)[0].split(" ");
        String path = req.length > 1 ? req[1] : "/";
        int q = path.indexOf('?');
        if (q >= 0) path = path.substring(0, q);
        if (path.equals("/")) path = "/index.html";
        OutputStream out = s.getOutputStream();
        byte[] body;
        String status = "200 OK";
        if (path.contains("..")) { body = null; } else {
            try (InputStream f = assets.open("web" + path)) {
                ByteArrayOutputStream b = new ByteArrayOutputStream();
                byte[] buf = new byte[16384];
                int n;
                while ((n = f.read(buf)) > 0) b.write(buf, 0, n);
                body = b.toByteArray();
            } catch (Exception e) { body = null; }
        }
        if (body == null) { status = "404 Not Found"; body = "not found".getBytes(StandardCharsets.UTF_8); path = ".txt"; }
        String type = path.endsWith(".html") ? "text/html; charset=utf-8"
                : path.endsWith(".js") || path.endsWith(".mjs") ? "text/javascript; charset=utf-8"
                : path.endsWith(".json") ? "application/json" : path.endsWith(".png") ? "image/png"
                : "text/plain; charset=utf-8";
        out.write(("HTTP/1.1 " + status + "\r\nContent-Type: " + type + "\r\nContent-Length: " + body.length
                + "\r\nCache-Control: no-cache\r\nConnection: close\r\n\r\n").getBytes(StandardCharsets.US_ASCII));
        out.write(body);
        out.flush();
        s.close();
    }

    void broadcast(String text) {
        byte[] p = text.getBytes(StandardCharsets.UTF_8);
        byte[] h;
        if (p.length < 126) h = new byte[]{(byte) 0x81, (byte) p.length};
        else h = new byte[]{(byte) 0x81, 126, (byte) (p.length >> 8), (byte) p.length};  // shots are < 64 KB
        for (OutputStream o : clients) {
            try {
                synchronized (o) { o.write(h); o.write(p); o.flush(); }
            } catch (Exception e) { clients.remove(o); }
        }
    }
}
