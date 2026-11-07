package com.meuamor.postador;

import android.content.ContentResolver;
import android.database.Cursor;
import android.net.Uri;
import android.provider.OpenableColumns;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/** Cliente mínimo da Graph API do Facebook (Páginas): textos, fotos e Reels. */
public class Graph {

    public static final String VERSAO = "v24.0";
    // Não é final só para os testes poderem apontar para um servidor falso.
    static String BASE = "https://graph.facebook.com/" + VERSAO + "/";

    public static final String[] PERMISSOES = {
            "pages_show_list", "pages_read_engagement", "pages_manage_posts"};

    /** Erro com mensagem já em português para mostrar na tela. */
    public static class ErroFacebook extends Exception {
        public ErroFacebook(String msg) { super(msg); }
    }

    /** Recebe mensagens de progresso (chamado fora da thread da tela). */
    public interface Progresso {
        void mostrar(String msg);
    }

    private final String pageId;
    private final String token;

    public Graph(String pageId, String token) {
        this.pageId = pageId;
        this.token = token;
    }

    // ------------------------------------------------------------------ conexão

    /** Troca o token de usuário de ~1h por um de longa duração. */
    public static String tokenLongo(String appId, String appSecret, String tokenCurto)
            throws ErroFacebook {
        Map<String, String> p = new LinkedHashMap<>();
        p.put("grant_type", "fb_exchange_token");
        p.put("client_id", appId);
        p.put("client_secret", appSecret);
        p.put("fb_exchange_token", tokenCurto);
        return obter(get("oauth/access_token", p), "access_token");
    }

    /** Páginas que o usuário administra (cada uma com id, name, access_token). */
    public static JSONArray paginas(String tokenUsuario) throws ErroFacebook {
        Map<String, String> p = new LinkedHashMap<>();
        p.put("fields", "id,name,access_token");
        p.put("limit", "100");
        p.put("access_token", tokenUsuario);
        JSONArray dados = get("me/accounts", p).optJSONArray("data");
        return dados == null ? new JSONArray() : dados;
    }

    /** Informações do token (expires_at, scopes). */
    public static JSONObject depurarToken(String tokenPagina, String appId, String appSecret)
            throws ErroFacebook {
        Map<String, String> p = new LinkedHashMap<>();
        p.put("input_token", tokenPagina);
        p.put("access_token", appId + "|" + appSecret);
        JSONObject r = get("debug_token", p).optJSONObject("data");
        return r == null ? new JSONObject() : r;
    }

    public JSONObject verificar() throws ErroFacebook {
        Map<String, String> p = new LinkedHashMap<>();
        p.put("fields", "id,name");
        p.put("access_token", token);
        return get(pageId, p);
    }

    // ------------------------------------------------------------------ posts

    /** Post de texto (com link opcional). agendado = segundos Unix, ou null para agora. */
    public String publicarTexto(String mensagem, Long agendado) throws ErroFacebook {
        Map<String, String> p = new LinkedHashMap<>();
        p.put("message", mensagem);
        agendar(p, agendado);
        return idDe(postForm(BASE + pageId + "/feed", p));
    }

    public String publicarFoto(ContentResolver cr, Uri foto, String legenda, Long agendado)
            throws ErroFacebook {
        Map<String, String> p = new LinkedHashMap<>();
        if (!legenda.isEmpty()) p.put("caption", legenda);
        agendar(p, agendado);
        return idDe(enviarFoto(cr, foto, p));
    }

    /** Várias fotos num só post: sobe cada uma sem publicar e depois anexa ao post. */
    public String publicarFotos(ContentResolver cr, List<Uri> fotos, String mensagem,
                                Long agendado, Progresso progresso) throws ErroFacebook {
        Map<String, String> post = new LinkedHashMap<>();
        if (!mensagem.isEmpty()) post.put("message", mensagem);
        for (int i = 0; i < fotos.size(); i++) {
            progresso.mostrar("Enviando foto " + (i + 1) + " de " + fotos.size() + "...");
            Map<String, String> p = new LinkedHashMap<>();
            p.put("published", "false");
            if (agendado != null) p.put("temporary", "true");
            String id = obter(enviarFoto(cr, fotos.get(i), p), "id");
            post.put("attached_media[" + i + "]", "{\"media_fbid\":\"" + id + "\"}");
        }
        progresso.mostrar("Criando o post...");
        agendar(post, agendado);
        return idDe(postForm(BASE + pageId + "/feed", post));
    }

    /** Reel: início -> envio do vídeo -> publicação/agendamento. Devolve o id do vídeo. */
    public String publicarReel(ContentResolver cr, Uri video, String descricao, Long agendado,
                               Progresso progresso) throws ErroFacebook {
        progresso.mostrar("Preparando o Reel...");
        Map<String, String> p = new LinkedHashMap<>();
        p.put("upload_phase", "start");
        JSONObject inicio = postForm(BASE + pageId + "/video_reels", p);
        String videoId = obter(inicio, "video_id");
        String urlEnvio = inicio.optString("upload_url",
                "https://rupload.facebook.com/video-upload/" + VERSAO + "/" + videoId);

        enviarVideo(cr, video, urlEnvio, progresso);

        progresso.mostrar(agendado == null ? "Publicando o Reel..." : "Agendando o Reel...");
        Map<String, String> fim = new LinkedHashMap<>();
        fim.put("upload_phase", "finish");
        fim.put("video_id", videoId);
        if (!descricao.isEmpty()) fim.put("description", descricao);
        if (agendado != null) {
            fim.put("video_state", "SCHEDULED");
            fim.put("scheduled_publish_time", String.valueOf(agendado));
        } else {
            fim.put("video_state", "PUBLISHED");
        }
        JSONObject r = postForm(BASE + pageId + "/video_reels", fim);
        if (!r.optBoolean("success", true)) {
            throw new ErroFacebook("O Facebook não finalizou o Reel: " + r);
        }
        return videoId;
    }

    /** Situação do processamento de um Reel, em texto. */
    public String statusVideo(String videoId) throws ErroFacebook {
        Map<String, String> p = new LinkedHashMap<>();
        p.put("fields", "status");
        p.put("access_token", token);
        JSONObject st = get(videoId, p).optJSONObject("status");
        return st == null ? "?" : st.optString("video_status", st.toString());
    }

    // ------------------------------------------------------------------ envio de arquivos

    private JSONObject enviarFoto(ContentResolver cr, Uri foto, Map<String, String> campos)
            throws ErroFacebook {
        campos.put("access_token", token);
        byte[] dados = lerTudo(cr, foto);
        String tipo = cr.getType(foto);
        if (tipo == null) tipo = "image/jpeg";
        String fronteira = UUID.randomUUID().toString().replace("-", "");
        ByteArrayOutputStream corpo = new ByteArrayOutputStream(dados.length + 2048);
        try {
            for (Map.Entry<String, String> e : campos.entrySet()) {
                corpo.write(("--" + fronteira + "\r\nContent-Disposition: form-data; name=\""
                        + e.getKey() + "\"\r\n\r\n" + e.getValue() + "\r\n")
                        .getBytes(StandardCharsets.UTF_8));
            }
            corpo.write(("--" + fronteira + "\r\nContent-Disposition: form-data; "
                    + "name=\"source\"; filename=\"foto\"\r\nContent-Type: " + tipo
                    + "\r\n\r\n").getBytes(StandardCharsets.UTF_8));
            corpo.write(dados);
            corpo.write(("\r\n--" + fronteira + "--\r\n").getBytes(StandardCharsets.UTF_8));
        } catch (IOException e) {
            throw new ErroFacebook("Erro ao preparar a foto: " + e.getMessage());
        }
        HttpURLConnection c = abrir(BASE + pageId + "/photos");
        c.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + fronteira);
        return enviar(c, corpo.toByteArray());
    }

    private void enviarVideo(ContentResolver cr, Uri video, String url, Progresso progresso)
            throws ErroFacebook {
        long tamanho = tamanho(cr, video);
        byte[] dados = null;
        if (tamanho <= 0) {
            dados = lerTudo(cr, video);
            tamanho = dados.length;
        }
        HttpURLConnection c = abrir(url);
        c.setRequestProperty("Authorization", "OAuth " + token);
        c.setRequestProperty("offset", "0");
        c.setRequestProperty("file_size", String.valueOf(tamanho));
        c.setRequestProperty("Content-Type", "application/octet-stream");
        c.setFixedLengthStreamingMode(tamanho);
        c.setReadTimeout(15 * 60 * 1000);
        String mb = String.format(java.util.Locale.ROOT, "%.1f", tamanho / 1e6);
        try (OutputStream out = c.getOutputStream();
             InputStream in = dados != null ? new java.io.ByteArrayInputStream(dados)
                     : cr.openInputStream(video)) {
            if (in == null) throw new ErroFacebook("Não foi possível abrir o vídeo.");
            byte[] buf = new byte[256 * 1024];
            long enviado = 0;
            int ultimo = -1;
            int n;
            while ((n = in.read(buf)) > 0) {
                out.write(buf, 0, n);
                enviado += n;
                int pct = (int) (enviado * 100 / tamanho);
                if (pct != ultimo) {
                    ultimo = pct;
                    progresso.mostrar("Enviando vídeo (" + mb + " MB): " + pct + "%");
                }
            }
        } catch (IOException e) {
            throw new ErroFacebook("Falha ao enviar o vídeo: " + e.getMessage());
        }
        JSONObject r = resposta(c);
        if (!r.optBoolean("success", true)) {
            throw new ErroFacebook("O Facebook não aceitou o vídeo: " + r);
        }
    }

    static long tamanho(ContentResolver cr, Uri uri) {
        try (Cursor cur = cr.query(uri, new String[]{OpenableColumns.SIZE}, null, null, null)) {
            if (cur != null && cur.moveToFirst() && !cur.isNull(0)) return cur.getLong(0);
        } catch (RuntimeException ignored) {
        }
        return -1;
    }

    static byte[] lerTudo(ContentResolver cr, Uri uri) throws ErroFacebook {
        try (InputStream in = cr.openInputStream(uri)) {
            if (in == null) throw new ErroFacebook("Não foi possível abrir o arquivo.");
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buf = new byte[64 * 1024];
            int n;
            while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
            return out.toByteArray();
        } catch (IOException e) {
            throw new ErroFacebook("Erro ao ler o arquivo: " + e.getMessage());
        }
    }

    // ------------------------------------------------------------------ HTTP

    private void agendar(Map<String, String> p, Long agendado) {
        if (agendado != null) {
            p.put("published", "false");
            p.put("scheduled_publish_time", String.valueOf(agendado));
        }
    }

    private JSONObject postForm(String url, Map<String, String> campos) throws ErroFacebook {
        campos.put("access_token", token);
        HttpURLConnection c = abrir(url);
        c.setRequestProperty("Content-Type", "application/x-www-form-urlencoded");
        return enviar(c, codificar(campos).getBytes(StandardCharsets.UTF_8));
    }

    static JSONObject get(String caminho, Map<String, String> campos) throws ErroFacebook {
        try {
            HttpURLConnection c = (HttpURLConnection)
                    new URL(BASE + caminho + "?" + codificar(campos)).openConnection();
            c.setConnectTimeout(30000);
            c.setReadTimeout(60000);
            return resposta(c);
        } catch (IOException e) {
            throw semConexao(e);
        }
    }

    private static HttpURLConnection abrir(String url) throws ErroFacebook {
        try {
            HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
            c.setRequestMethod("POST");
            c.setDoOutput(true);
            c.setConnectTimeout(30000);
            c.setReadTimeout(5 * 60 * 1000);
            return c;
        } catch (IOException e) {
            throw semConexao(e);
        }
    }

    private static JSONObject enviar(HttpURLConnection c, byte[] corpo) throws ErroFacebook {
        c.setFixedLengthStreamingMode(corpo.length);
        try (OutputStream out = c.getOutputStream()) {
            out.write(corpo);
        } catch (IOException e) {
            throw semConexao(e);
        }
        return resposta(c);
    }

    private static JSONObject resposta(HttpURLConnection c) throws ErroFacebook {
        int codigo;
        String texto;
        try {
            codigo = c.getResponseCode();
            InputStream in = codigo >= 400 ? c.getErrorStream() : c.getInputStream();
            texto = in == null ? "" : new String(lerStream(in), StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw semConexao(e);
        } finally {
            c.disconnect();
        }
        JSONObject json;
        try {
            json = texto.isEmpty() ? new JSONObject() : new JSONObject(texto);
        } catch (JSONException e) {
            throw new ErroFacebook("Resposta inesperada do Facebook (HTTP " + codigo + ").");
        }
        if (codigo >= 400 || json.has("error")) throw new ErroFacebook(mensagemDeErro(json, codigo));
        return json;
    }

    static String mensagemDeErro(JSONObject json, int http) {
        JSONObject erro = json.optJSONObject("error");
        if (erro == null) erro = json.optJSONObject("debug_info");
        if (erro == null) return "Erro HTTP " + http + " do Facebook.";
        int codigo = erro.optInt("code", 0);
        String msg = erro.optString("message", "Erro HTTP " + http);
        if (codigo == 190) {
            msg += "\n\nO token é inválido ou expirou. Conecte a Página de novo na aba Conta.";
        } else if (codigo == 10 || codigo == 200) {
            msg += "\n\nFalta permissão: o token precisa de pages_manage_posts e "
                    + "pages_read_engagement, e você precisa ser administrador da Página.";
        }
        return "Facebook recusou (" + codigo + "): " + msg;
    }

    private static ErroFacebook semConexao(IOException e) {
        return new ErroFacebook("Sem conexão com o Facebook. Verifique a internet. ("
                + e.getClass().getSimpleName() + ")");
    }

    private static byte[] lerStream(InputStream in) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buf = new byte[16 * 1024];
        int n;
        while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
        in.close();
        return out.toByteArray();
    }

    static String codificar(Map<String, String> campos) {
        StringBuilder sb = new StringBuilder();
        try {
            for (Map.Entry<String, String> e : campos.entrySet()) {
                if (sb.length() > 0) sb.append('&');
                sb.append(URLEncoder.encode(e.getKey(), "UTF-8")).append('=')
                        .append(URLEncoder.encode(e.getValue(), "UTF-8"));
            }
        } catch (java.io.UnsupportedEncodingException impossivel) {
            throw new RuntimeException(impossivel);
        }
        return sb.toString();
    }

    private static String obter(JSONObject json, String campo) throws ErroFacebook {
        String v = json.optString(campo, "");
        if (v.isEmpty()) throw new ErroFacebook("Resposta do Facebook sem \"" + campo + "\": " + json);
        return v;
    }

    private static String idDe(JSONObject r) {
        String id = r.optString("post_id", "");
        return id.isEmpty() ? r.optString("id", "?") : id;
    }
}
