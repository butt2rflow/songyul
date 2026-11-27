package org.songyul.r10bridge;

import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.MediaStore;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

/** Appends one JSON line per shot (and per raw message) to Download/R10Bridge/, so the files are easy to copy off. */
class ShotStore {
    private static final String DIR = Environment.DIRECTORY_DOWNLOADS + "/R10Bridge/";
    private final Context ctx;
    // MediaStore may add an extension to the display name (".txt", ".json"), so a later lookup by name misses and
    // every append would make a new file. Keep the Uri of each file once created instead.
    private final Map<String, Uri> uris = new HashMap<>();

    ShotStore(Context ctx) { this.ctx = ctx.getApplicationContext(); }

    static String today() { return new SimpleDateFormat("yyyyMMdd", Locale.US).format(new Date()); }

    void appendShot(String jsonLine) { append("r10-shots-" + today() + ".jsonl", jsonLine); }

    void appendRaw(String line) { append("r10-raw-" + today() + ".txt", line); }

    private synchronized void append(String name, String line) {
        byte[] bytes = (line + "\n").getBytes(StandardCharsets.UTF_8);
        try {
            if (Build.VERSION.SDK_INT >= 29) {
                Uri uri = findOrCreate(name);
                try (OutputStream o = ctx.getContentResolver().openOutputStream(uri, "wa")) { o.write(bytes); }
            } else {
                File d = new File(ctx.getExternalFilesDir(null), "R10Bridge");
                if (!d.exists()) d.mkdirs();
                try (FileOutputStream o = new FileOutputStream(new File(d, name), true)) { o.write(bytes); }
            }
        } catch (Exception ignored) { }
    }

    private Uri findOrCreate(String name) {
        Uri known = uris.get(name);
        if (known != null) return known;
        ContentResolver cr = ctx.getContentResolver();
        Uri coll = MediaStore.Downloads.EXTERNAL_CONTENT_URI;
        try (Cursor c = cr.query(coll, new String[]{MediaStore.MediaColumns._ID},
                MediaStore.MediaColumns.DISPLAY_NAME + "=? AND " + MediaStore.MediaColumns.RELATIVE_PATH + "=?",
                new String[]{name, DIR}, null)) {
            if (c != null && c.moveToFirst()) {
                Uri u = Uri.withAppendedPath(coll, String.valueOf(c.getLong(0)));
                uris.put(name, u);
                return u;
            }
        }
        ContentValues v = new ContentValues();
        v.put(MediaStore.MediaColumns.DISPLAY_NAME, name);
        v.put(MediaStore.MediaColumns.MIME_TYPE, name.endsWith(".txt") ? "text/plain" : "application/octet-stream");
        v.put(MediaStore.MediaColumns.RELATIVE_PATH, DIR);
        Uri u = cr.insert(coll, v);
        if (u != null) uris.put(name, u);
        return u;
    }
}
