package com.meuamor.reels;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.PendingIntent;
import android.app.ProgressDialog;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageInstaller;
import android.net.Uri;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.concurrent.Executors;

/**
 * Atualização automática: consulta a última Release do GitHub (gerada pelo GitHub Actions a cada
 * modificação) e, se houver versão mais nova, baixa e instala o APK por cima do atual.
 */
final class Updater {
    static final String LATEST_URL = "https://api.github.com/repos/mika4747/Meu_Amor/releases/latest";
    private static final String ACTION_INSTALL_STATUS = "com.meuamor.reels.INSTALL_STATUS";

    private Updater() {}

    /** @param manual true quando o usuário tocou em "Verificar atualização" (mostra "já está atualizado"). */
    static void check(Activity act, boolean manual) {
        Handler ui = new Handler(Looper.getMainLooper());
        Executors.newSingleThreadExecutor().execute(() -> {
            try {
                JSONObject rel = new JSONObject(httpGet(LATEST_URL));
                int remote = parseVersion(rel.optString("tag_name"));
                int local = currentVersion(act);
                String apkUrl = null;
                JSONArray assets = rel.optJSONArray("assets");
                for (int i = 0; assets != null && i < assets.length(); i++) {
                    JSONObject a = assets.getJSONObject(i);
                    if (a.optString("name").endsWith(".apk")) apkUrl = a.optString("browser_download_url");
                }
                final String url = apkUrl;
                final String notes = rel.optString("body", "").trim();
                ui.post(() -> {
                    if (act.isFinishing()) return;
                    if (remote > local && url != null) {
                        new AlertDialog.Builder(act)
                                .setTitle("Nova versão disponível 🎉")
                                .setMessage("Versão " + remote + " (você tem a " + local + ")."
                                        + (notes.isEmpty() ? "" : "\n\n" + truncate(notes, 600)))
                                .setPositiveButton("Atualizar", (d, w) -> startUpdate(act, url))
                                .setNegativeButton("Depois", null)
                                .show();
                    } else if (manual) {
                        Toast.makeText(act, "Você já tem a versão mais recente (" + local + ") ✅", Toast.LENGTH_SHORT).show();
                    }
                });
            } catch (Exception e) {
                if (manual) ui.post(() -> Toast.makeText(act, "Não consegui verificar: " + e.getMessage(), Toast.LENGTH_LONG).show());
            }
        });
    }

    static int currentVersion(Context ctx) {
        try {
            PackageInfo pi = ctx.getPackageManager().getPackageInfo(ctx.getPackageName(), 0);
            return Build.VERSION.SDK_INT >= 28 ? (int) pi.getLongVersionCode() : pi.versionCode;
        } catch (Exception e) {
            return 0;
        }
    }

    /** "v105" -> 105 */
    static int parseVersion(String tag) {
        String digits = tag == null ? "" : tag.replaceAll("[^0-9]", "");
        try { return digits.isEmpty() ? 0 : Integer.parseInt(digits); } catch (NumberFormatException e) { return 0; }
    }

    private static String truncate(String s, int max) { return s.length() <= max ? s : s.substring(0, max) + "…"; }

    private static void startUpdate(Activity act, String apkUrl) {
        if (Build.VERSION.SDK_INT >= 26 && !act.getPackageManager().canRequestPackageInstalls()) {
            new AlertDialog.Builder(act)
                    .setTitle("Permitir atualizações")
                    .setMessage("Na próxima tela, ative \"Permitir desta fonte\" para o Meu Bot Reels e depois volte e toque em Atualizar de novo.")
                    .setPositiveButton("Abrir configurações", (d, w) -> act.startActivity(
                            new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + act.getPackageName()))))
                    .setNegativeButton("Cancelar", null)
                    .show();
            return;
        }
        @SuppressWarnings("deprecation")
        ProgressDialog pd = new ProgressDialog(act);
        pd.setTitle("Baixando atualização…");
        pd.setProgressStyle(ProgressDialog.STYLE_HORIZONTAL);
        pd.setMax(100);
        pd.setCancelable(false);
        pd.show();
        Handler ui = new Handler(Looper.getMainLooper());
        Context app = act.getApplicationContext();
        Executors.newSingleThreadExecutor().execute(() -> {
            try {
                PackageInstaller installer = app.getPackageManager().getPackageInstaller();
                PackageInstaller.SessionParams params =
                        new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL);
                params.setAppPackageName(app.getPackageName());
                int sessionId = installer.createSession(params);
                try (PackageInstaller.Session session = installer.openSession(sessionId)) {
                    HttpURLConnection c = (HttpURLConnection) new URL(apkUrl).openConnection();
                    c.setInstanceFollowRedirects(true);
                    c.setConnectTimeout(30_000);
                    c.setReadTimeout(120_000);
                    long total = c.getContentLengthLong();
                    try (InputStream in = c.getInputStream();
                         OutputStream out = session.openWrite("app.apk", 0, total > 0 ? total : -1)) {
                        byte[] buf = new byte[64 * 1024];
                        long done = 0;
                        int n;
                        while ((n = in.read(buf)) != -1) {
                            out.write(buf, 0, n);
                            done += n;
                            if (total > 0) {
                                int pct = (int) (done * 100 / total);
                                ui.post(() -> pd.setProgress(pct));
                            }
                        }
                        session.fsync(out);
                    }
                    Intent cb = new Intent(app, InstallReceiver.class).setAction(ACTION_INSTALL_STATUS);
                    int flags = PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= 31 ? PendingIntent.FLAG_MUTABLE : 0);
                    PendingIntent pi = PendingIntent.getBroadcast(app, sessionId, cb, flags);
                    session.commit(pi.getIntentSender());
                }
                ui.post(pd::dismiss);
            } catch (Exception e) {
                ui.post(() -> {
                    pd.dismiss();
                    new AlertDialog.Builder(act).setTitle("Falha na atualização")
                            .setMessage(String.valueOf(e.getMessage())).setPositiveButton("OK", null).show();
                });
            }
        });
    }

    private static String httpGet(String url) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setRequestProperty("Accept", "application/vnd.github+json");
        c.setConnectTimeout(15_000);
        c.setReadTimeout(30_000);
        int code = c.getResponseCode();
        if (code == 404) throw new Exception("nenhuma versão publicada ainda");
        if (code >= 400) throw new Exception("HTTP " + code);
        try (InputStream in = c.getInputStream()) {
            ByteArrayOutputStream bos = new ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) != -1) bos.write(buf, 0, n);
            return bos.toString("UTF-8");
        }
    }

    /** Recebe o resultado do PackageInstaller e abre a tela de confirmação do Android. */
    public static class InstallReceiver extends BroadcastReceiver {
        @Override
        public void onReceive(Context ctx, Intent intent) {
            int status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE);
            if (status == PackageInstaller.STATUS_PENDING_USER_ACTION) {
                @SuppressWarnings("deprecation")
                Intent confirm = intent.getParcelableExtra(Intent.EXTRA_INTENT);
                if (confirm != null) {
                    confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                    ctx.startActivity(confirm);
                }
            } else if (status != PackageInstaller.STATUS_SUCCESS) {
                String msg = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE);
                Toast.makeText(ctx, "Atualização não instalada: " + msg, Toast.LENGTH_LONG).show();
            }
        }
    }
}
