package com.meuamor.reels;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Map;

import org.json.JSONException;
import org.json.JSONObject;

/** Chamadas HTTP para a Graph API do Facebook. Executar sempre fora da thread principal. */
final class Graph {
    static final String VERSION = "v23.0";
    static final String BASE = "https://graph.facebook.com/" + VERSION + "/";

    interface Progress { void onProgress(long sent, long total); }

    private Graph() {}

    static String encode(Map<String, String> params) {
        StringBuilder sb = new StringBuilder();
        for (Map.Entry<String, String> e : params.entrySet()) {
            if (e.getValue() == null) continue;
            if (sb.length() > 0) sb.append('&');
            sb.append(urlEncode(e.getKey())).append('=').append(urlEncode(e.getValue()));
        }
        return sb.toString();
    }

    private static String urlEncode(String s) {
        try {
            return URLEncoder.encode(s, "UTF-8");  // versão compatível com Android 7+
        } catch (java.io.UnsupportedEncodingException e) {
            throw new AssertionError(e);
        }
    }

    static JSONObject get(String path, Map<String, String> params) throws IOException {
        HttpURLConnection c = open(BASE + path + "?" + encode(params));
        c.setRequestMethod("GET");
        return read(c);
    }

    static JSONObject post(String path, Map<String, String> params) throws IOException {
        HttpURLConnection c = open(BASE + path);
        c.setRequestMethod("POST");
        c.setDoOutput(true);
        c.setRequestProperty("Content-Type", "application/x-www-form-urlencoded; charset=utf-8");
        byte[] body = encode(params).getBytes(StandardCharsets.UTF_8);
        c.setFixedLengthStreamingMode(body.length);
        try (OutputStream os = c.getOutputStream()) { os.write(body); }
        return read(c);
    }

    /** Envia o vídeo para o endereço de upload do Reel (rupload.facebook.com). */
    static JSONObject uploadVideo(String uploadUrl, String pageToken, InputStream in, long size,
                                  Progress progress) throws IOException {
        HttpURLConnection c = open(uploadUrl);
        c.setRequestMethod("POST");
        c.setDoOutput(true);
        c.setReadTimeout(10 * 60 * 1000);
        c.setRequestProperty("Authorization", "OAuth " + pageToken);
        c.setRequestProperty("offset", "0");
        c.setRequestProperty("file_size", String.valueOf(size));
        c.setRequestProperty("Content-Type", "application/octet-stream");
        c.setFixedLengthStreamingMode(size);
        byte[] buf = new byte[256 * 1024];
        long sent = 0;
        try (OutputStream os = c.getOutputStream()) {
            int n;
            while ((n = in.read(buf)) != -1) {
                os.write(buf, 0, n);
                sent += n;
                if (progress != null) progress.onProgress(sent, size);
            }
        }
        return read(c);
    }

    private static HttpURLConnection open(String url) throws IOException {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(30_000);
        c.setReadTimeout(120_000);
        return c;
    }

    private static JSONObject read(HttpURLConnection c) throws IOException {
        int code = c.getResponseCode();
        InputStream is = code >= 400 ? c.getErrorStream() : c.getInputStream();
        String text = "";
        if (is != null) {
            ByteArrayOutputStream bos = new ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            int n;
            while ((n = is.read(buf)) != -1) bos.write(buf, 0, n);
            is.close();
            text = bos.toString("UTF-8");
        }
        c.disconnect();
        JSONObject json;
        try {
            json = new JSONObject(text);
        } catch (JSONException e) {
            if (code >= 400) throw new IOException("HTTP " + code + ": " + text);
            json = new JSONObject();
        }
        JSONObject err = json.optJSONObject("error");
        if (err != null) throw new IOException(err.optString("message", "Erro desconhecido"));
        if (code >= 400) throw new IOException("HTTP " + code);
        return json;
    }
}
