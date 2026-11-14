package com.meuamor.reels;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.DatePickerDialog;
import android.app.TimePickerDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.OpenableColumns;
import android.view.View;
import android.view.WindowManager;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.Spinner;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.InputStream;
import java.text.DateFormat;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {
    private static final int REQ_PICK_VIDEO = 1;
    private static final String PREFS = "bot";

    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private final Handler ui = new Handler(Looper.getMainLooper());
    private SharedPreferences prefs;

    private LinearLayout setupSection, mainSection;
    private EditText tokenInput, appIdInput, appSecretInput, captionInput, postInput, linkInput;
    private Spinner pageSpinner;
    private TextView videoName, statusText, scheduleText;
    private CheckBox scheduleCheck;
    private Button publishButton, postButton, connectButton;
    private ProgressBar progress;

    private final List<JSONObject> pages = new ArrayList<>();
    private Uri videoUri;
    private Calendar scheduleAt;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);

        setupSection = findViewById(R.id.setupSection);
        mainSection = findViewById(R.id.mainSection);
        tokenInput = findViewById(R.id.tokenInput);
        appIdInput = findViewById(R.id.appIdInput);
        appSecretInput = findViewById(R.id.appSecretInput);
        captionInput = findViewById(R.id.captionInput);
        postInput = findViewById(R.id.postInput);
        linkInput = findViewById(R.id.linkInput);
        pageSpinner = findViewById(R.id.pageSpinner);
        videoName = findViewById(R.id.videoName);
        statusText = findViewById(R.id.statusText);
        scheduleText = findViewById(R.id.scheduleText);
        scheduleCheck = findViewById(R.id.scheduleCheck);
        publishButton = findViewById(R.id.publishButton);
        postButton = findViewById(R.id.postButton);
        connectButton = findViewById(R.id.connectButton);
        progress = findViewById(R.id.progress);

        connectButton.setOnClickListener(v -> connect());
        findViewById(R.id.pickVideoButton).setOnClickListener(v -> pickVideo());
        publishButton.setOnClickListener(v -> publishReel());
        postButton.setOnClickListener(v -> publishPost());
        findViewById(R.id.logoutButton).setOnClickListener(v -> new AlertDialog.Builder(this)
                .setMessage("Remover o token salvo e conectar outra conta?")
                .setPositiveButton("Sim", (d, w) -> {
                    prefs.edit().clear().apply();
                    showSetup();
                })
                .setNegativeButton("Cancelar", null)
                .show());
        scheduleCheck.setOnCheckedChangeListener((b, checked) -> {
            if (checked) pickSchedule();
            else { scheduleAt = null; scheduleText.setText(""); }
        });

        loadPages();
        if (pages.isEmpty()) showSetup(); else showMain();
        handleShareIntent(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        handleShareIntent(intent);
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        worker.shutdown();
    }

    // ------------------------------------------------------------------ telas

    private void showSetup() {
        setupSection.setVisibility(View.VISIBLE);
        mainSection.setVisibility(View.GONE);
        setTitle("Configurar");
    }

    private void showMain() {
        setupSection.setVisibility(View.GONE);
        mainSection.setVisibility(View.VISIBLE);
        setTitle(R.string.app_name);
        List<String> names = new ArrayList<>();
        for (JSONObject p : pages) names.add(p.optString("name"));
        ArrayAdapter<String> adapter = new ArrayAdapter<>(this, android.R.layout.simple_spinner_item, names);
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        pageSpinner.setAdapter(adapter);
        pageSpinner.setSelection(Math.min(prefs.getInt("selected", 0), Math.max(0, pages.size() - 1)));
    }

    private void loadPages() {
        pages.clear();
        try {
            JSONArray arr = new JSONArray(prefs.getString("pages", "[]"));
            for (int i = 0; i < arr.length(); i++) pages.add(arr.getJSONObject(i));
        } catch (JSONException ignored) { }
    }

    private JSONObject currentPage() {
        int i = pageSpinner.getSelectedItemPosition();
        prefs.edit().putInt("selected", i).apply();
        return pages.get(Math.max(0, i));
    }

    // ------------------------------------------------------------------ conectar

    private void connect() {
        String token = tokenInput.getText().toString().trim();
        String appId = appIdInput.getText().toString().trim();
        String secret = appSecretInput.getText().toString().trim();
        if (token.isEmpty()) { toast("Cole o token primeiro"); return; }
        connectButton.setEnabled(false);
        connectButton.setText("Conectando…");
        worker.execute(() -> {
            try {
                String userToken = token;
                if (!appId.isEmpty() && !secret.isEmpty()) {
                    Map<String, String> p = new HashMap<>();
                    p.put("grant_type", "fb_exchange_token");
                    p.put("client_id", appId);
                    p.put("client_secret", secret);
                    p.put("fb_exchange_token", token);
                    userToken = Graph.get("oauth/access_token", p).getString("access_token");
                }
                Map<String, String> p = new HashMap<>();
                p.put("fields", "id,name,access_token");
                p.put("limit", "100");
                p.put("access_token", userToken);
                JSONArray data = Graph.get("me/accounts", p).optJSONArray("data");
                if (data == null || data.length() == 0)
                    throw new Exception("Nenhuma página encontrada. Confira as permissões do token.");
                JSONArray slim = new JSONArray();
                for (int i = 0; i < data.length(); i++) {
                    JSONObject d = data.getJSONObject(i);
                    slim.put(new JSONObject().put("id", d.getString("id"))
                            .put("name", d.optString("name"))
                            .put("token", d.getString("access_token")));
                }
                prefs.edit().putString("pages", slim.toString()).putInt("selected", 0).apply();
                ui.post(() -> {
                    loadPages();
                    tokenInput.setText("");
                    appSecretInput.setText("");
                    showMain();
                    toast(pages.size() + " página(s) conectada(s) ✅");
                });
            } catch (Exception e) {
                ui.post(() -> alert("Não foi possível conectar", e.getMessage()));
            } finally {
                ui.post(() -> { connectButton.setEnabled(true); connectButton.setText("Conectar"); });
            }
        });
    }

    // ------------------------------------------------------------------ vídeo

    private void handleShareIntent(Intent intent) {
        if (intent != null && Intent.ACTION_SEND.equals(intent.getAction())) {
            @SuppressWarnings("deprecation")
            Uri uri = intent.getParcelableExtra(Intent.EXTRA_STREAM);
            if (uri != null) setVideo(uri);
        }
    }

    private void pickVideo() {
        Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        i.addCategory(Intent.CATEGORY_OPENABLE);
        i.setType("video/*");
        startActivityForResult(i, REQ_PICK_VIDEO);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQ_PICK_VIDEO && resultCode == RESULT_OK && data != null && data.getData() != null) {
            setVideo(data.getData());
        }
    }

    private void setVideo(Uri uri) {
        videoUri = uri;
        long size = fileSize(uri);
        videoName.setText("📹 " + fileName(uri) + (size > 0 ? String.format(" (%.1f MB)", size / 1048576.0) : ""));
    }

    private String fileName(Uri uri) {
        try (Cursor c = getContentResolver().query(uri, null, null, null, null)) {
            if (c != null && c.moveToFirst()) {
                int i = c.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                if (i >= 0) return c.getString(i);
            }
        } catch (Exception ignored) { }
        return uri.getLastPathSegment();
    }

    private long fileSize(Uri uri) {
        try (Cursor c = getContentResolver().query(uri, null, null, null, null)) {
            if (c != null && c.moveToFirst()) {
                int i = c.getColumnIndex(OpenableColumns.SIZE);
                if (i >= 0 && !c.isNull(i)) return c.getLong(i);
            }
        } catch (Exception ignored) { }
        try (android.content.res.AssetFileDescriptor fd = getContentResolver().openAssetFileDescriptor(uri, "r")) {
            if (fd != null) return fd.getLength();
        } catch (Exception ignored) { }
        return -1;
    }

    // ------------------------------------------------------------------ agendamento

    private void pickSchedule() {
        Calendar now = Calendar.getInstance();
        now.add(Calendar.HOUR_OF_DAY, 1);
        DatePickerDialog dp = new DatePickerDialog(this, (v, y, m, d) -> {
            Calendar cal = Calendar.getInstance();
            cal.set(y, m, d);
            new TimePickerDialog(this, (tv, h, min) -> {
                cal.set(Calendar.HOUR_OF_DAY, h);
                cal.set(Calendar.MINUTE, min);
                cal.set(Calendar.SECOND, 0);
                scheduleAt = cal;
                scheduleText.setText(DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.SHORT).format(cal.getTime()));
            }, now.get(Calendar.HOUR_OF_DAY), 0, true).show();
        }, now.get(Calendar.YEAR), now.get(Calendar.MONTH), now.get(Calendar.DAY_OF_MONTH));
        dp.setOnCancelListener(d -> scheduleCheck.setChecked(false));
        dp.show();
    }

    // ------------------------------------------------------------------ publicar Reel

    private void publishReel() {
        if (videoUri == null) { toast("Escolha um vídeo"); return; }
        Long when = null;
        if (scheduleCheck.isChecked()) {
            if (scheduleAt == null) { toast("Escolha a data do agendamento"); return; }
            long secs = scheduleAt.getTimeInMillis() / 1000;
            long nowSecs = System.currentTimeMillis() / 1000;
            if (secs < nowSecs + 10 * 60 || secs > nowSecs + 29L * 24 * 3600) {
                alert("Data inválida", "O agendamento precisa ser entre 10 minutos e 29 dias a partir de agora.");
                return;
            }
            when = secs;
        }
        final Long scheduled = when;
        final JSONObject page = currentPage();
        final String caption = captionInput.getText().toString();
        final Uri uri = videoUri;
        final String whenLabel = scheduleText.getText().toString();
        final long size = fileSize(uri);
        if (size <= 0) { alert("Erro", "Não consegui ler o tamanho do vídeo."); return; }

        setBusy(true);
        status("Iniciando upload…");
        worker.execute(() -> {
            String pageId = page.optString("id");
            String token = page.optString("token");
            try {
                // 1) start
                Map<String, String> p = new HashMap<>();
                p.put("upload_phase", "start");
                p.put("access_token", token);
                JSONObject start = Graph.post(pageId + "/video_reels", p);
                String videoId = start.getString("video_id");
                String uploadUrl = start.optString("upload_url",
                        "https://rupload.facebook.com/video-upload/" + Graph.VERSION + "/" + videoId);

                // 2) upload
                try (InputStream in = getContentResolver().openInputStream(uri)) {
                    if (in == null) throw new Exception("Não consegui abrir o vídeo");
                    Graph.uploadVideo(uploadUrl, token, in, size, (sent, total) -> ui.post(() -> {
                        int pct = (int) (sent * 100 / total);
                        progress.setProgress(pct);
                        status("Enviando vídeo… " + pct + "%");
                    }));
                }

                // 3) finish
                status("Finalizando…");
                p = new HashMap<>();
                p.put("upload_phase", "finish");
                p.put("video_id", videoId);
                p.put("description", caption);
                p.put("access_token", token);
                if (scheduled != null) {
                    p.put("video_state", "SCHEDULED");
                    p.put("scheduled_publish_time", String.valueOf(scheduled));
                } else {
                    p.put("video_state", "PUBLISHED");
                }
                Graph.post(pageId + "/video_reels", p);

                if (scheduled != null) {
                    done("✅ Reel agendado para " + whenLabel + "!", true);
                    return;
                }

                // 4) acompanhar processamento
                for (int i = 0; i < 120; i++) {
                    Map<String, String> q = new HashMap<>();
                    q.put("fields", "status,permalink_url");
                    q.put("access_token", token);
                    JSONObject info = Graph.get(videoId, q);
                    JSONObject st = info.optJSONObject("status");
                    String vs = st != null ? st.optString("video_status") : "";
                    if ("ready".equals(vs) || "published".equals(vs)) {
                        done("✅ Reel publicado!\n" + info.optString("permalink_url", "ID: " + videoId), true);
                        return;
                    }
                    if ("error".equals(vs)) throw new Exception("O Facebook rejeitou o vídeo. Ele é vertical e tem entre 3 e 90 segundos?");
                    status("Processando no Facebook… (" + (vs.isEmpty() ? "aguarde" : vs) + ")");
                    Thread.sleep(5000);
                }
                done("⏳ Enviado! O Facebook ainda está processando. Confira na página daqui a pouco.\nID: " + videoId, true);
            } catch (Exception e) {
                done("❌ Erro: " + e.getMessage(), false);
            }
        });
    }

    // ------------------------------------------------------------------ post de texto

    private void publishPost() {
        String msg = postInput.getText().toString().trim();
        String link = linkInput.getText().toString().trim();
        if (msg.isEmpty() && link.isEmpty()) { toast("Escreva algo"); return; }
        JSONObject page = currentPage();
        postButton.setEnabled(false);
        worker.execute(() -> {
            try {
                Map<String, String> p = new HashMap<>();
                p.put("message", msg);
                if (!link.isEmpty()) p.put("link", link);
                p.put("access_token", page.optString("token"));
                Graph.post(page.optString("id") + "/feed", p);
                ui.post(() -> { postInput.setText(""); linkInput.setText(""); toast("Post publicado ✅"); });
            } catch (Exception e) {
                ui.post(() -> alert("Erro ao publicar", e.getMessage()));
            } finally {
                ui.post(() -> postButton.setEnabled(true));
            }
        });
    }

    // ------------------------------------------------------------------ util

    private void setBusy(boolean busy) {
        publishButton.setEnabled(!busy);
        publishButton.setText(busy ? "Publicando… não feche o app" : "Publicar Reel");
        progress.setVisibility(busy ? View.VISIBLE : View.GONE);
        progress.setProgress(0);
        if (busy) getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        else getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    }

    private void done(String msg, boolean success) {
        ui.post(() -> {
            setBusy(false);
            statusText.setText(msg);
            if (success) {
                videoUri = null;
                videoName.setText("Nenhum vídeo escolhido (vertical, 3 a 90 s)");
                captionInput.setText("");
                scheduleCheck.setChecked(false);
            }
        });
    }

    private void status(String msg) { ui.post(() -> statusText.setText(msg)); }

    private void toast(String msg) { Toast.makeText(this, msg, Toast.LENGTH_SHORT).show(); }

    private void alert(String title, String msg) {
        new AlertDialog.Builder(this).setTitle(title).setMessage(msg).setPositiveButton("OK", null).show();
    }
}
