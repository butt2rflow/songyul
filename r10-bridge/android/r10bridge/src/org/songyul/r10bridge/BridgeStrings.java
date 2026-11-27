package org.songyul.r10bridge;

import android.content.Context;
import android.content.res.Configuration;

import java.util.Locale;

final class BridgeStrings {
    private static final String LANGUAGE = "language";

    static String language(Context context) {
        String saved = context.getSharedPreferences("settings", Context.MODE_PRIVATE).getString(LANGUAGE, "");
        if (saved.equals("ko") || saved.equals("en")) return saved;
        return context.getResources().getConfiguration().getLocales().get(0).getLanguage().equals("ko") ? "ko" : "en";
    }

    static void saveLanguage(Context context, String language) {
        context.getSharedPreferences("settings", Context.MODE_PRIVATE).edit().putString(LANGUAGE, language).apply();
    }

    static Context localized(Context context) {
        Configuration config = new Configuration(context.getResources().getConfiguration());
        config.setLocale(Locale.forLanguageTag(language(context)));
        return context.createConfigurationContext(config);
    }
}
