package com.meuamor.postador;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import android.content.ContentResolver;
import android.net.Uri;

import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.LinkedList;
import java.util.List;
import java.util.Map;

import static org.robolectric.Shadows.shadowOf;

/** Testa o código HTTP de verdade contra um "Facebook" falso rodando localmente. */
@RunWith(RobolectricTestRunner.class)
public class GraphTest {

    /** Uma requisição recebida pelo servidor falso. */
    static class Pedido {
        String metodo, caminho, query, tipo;
        Map<String, String> cabecalhos = new HashMap<>();
        byte[] corpo;

        Map<String, String> form() {
            Map<String, String> m = new HashMap<>();
            String texto = new String(corpo, StandardCharsets.UTF_8);
            for (String par : texto.split("&")) {
                if (par.isEmpty()) continue;
                String[] kv = par.split("=", 2);
                try {
                    m.put(URLDecoder.decode(kv[0], "UTF-8"),
                            kv.length > 1 ? URLDecoder.decode(kv[1], "UTF-8") : "");
                } catch (java.io.UnsupportedEncodingException e) {
                    throw new RuntimeException(e);
                }
            }
            return m;
        }

        String corpoTexto() { return new String(corpo, StandardCharsets.ISO_8859_1); }
    }

    private ServerSocket servidor;
    private Thread atendente;
    private final List<Pedido> pedidos = new ArrayList<>();
    private final LinkedList<String[]> respostas = new LinkedList<>(); // {status, json}
    private String base;

    @Before
    public void iniciar() throws Exception {
        servidor = new ServerSocket(0, 50, InetAddress.getByName("127.0.0.1"));
        base = "http://127.0.0.1:" + servidor.getLocalPort() + "/";
        Graph.BASE = base;
        atendente = new Thread(() -> {
            while (!servidor.isClosed()) {
                try (Socket s = servidor.accept()) {
                    atender(s);
                } catch (Exception ignorado) {
                    // servidor fechado no fim do teste
                }
            }
        });
        atendente.start();
    }

    /** Servidor HTTP/1.1 mínimo: lê uma requisição e responde com o próximo JSON. */
    private void atender(Socket s) throws Exception {
        InputStream in = s.getInputStream();
        String linha = lerLinha(in);
        Pedido p = new Pedido();
        String[] partes = linha.split(" ");
        p.metodo = partes[0];
        String alvo = partes[1];
        int q = alvo.indexOf('?');
        p.caminho = q < 0 ? alvo : alvo.substring(0, q);
        p.query = q < 0 ? null : alvo.substring(q + 1);
        for (String h = lerLinha(in); !h.isEmpty(); h = lerLinha(in)) {
            int i = h.indexOf(':');
            p.cabecalhos.put(h.substring(0, i).trim().toLowerCase(), h.substring(i + 1).trim());
        }
        int tamanho = Integer.parseInt(p.cabecalhos.getOrDefault("content-length", "0"));
        p.corpo = new byte[tamanho];
        int lidos = 0;
        while (lidos < tamanho) {
            int n = in.read(p.corpo, lidos, tamanho - lidos);
            if (n < 0) break;
            lidos += n;
        }
        String[] r;
        synchronized (pedidos) {
            pedidos.add(p);
            r = respostas.isEmpty() ? new String[]{"200", "{}"} : respostas.removeFirst();
        }
        byte[] json = r[1].replace("$BASE", base).getBytes(StandardCharsets.UTF_8);
        OutputStream out = s.getOutputStream();
        out.write(("HTTP/1.1 " + r[0] + " X\r\nContent-Type: application/json\r\n"
                + "Content-Length: " + json.length + "\r\nConnection: close\r\n\r\n")
                .getBytes(StandardCharsets.UTF_8));
        out.write(json);
        out.flush();
    }

    private static String lerLinha(InputStream in) throws Exception {
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        int c;
        while ((c = in.read()) >= 0 && c != '\n') if (c != '\r') b.write(c);
        return b.toString("UTF-8");
    }

    @After
    public void parar() throws Exception {
        servidor.close();
        atendente.join(2000);
    }

    private void responder(String json) { respostas.add(new String[]{"200", json}); }

    private Uri arquivo(String nome, byte[] dados) {
        Uri uri = Uri.parse("content://teste/" + nome);
        ContentResolver cr = RuntimeEnvironment.getApplication().getContentResolver();
        shadowOf(cr).registerInputStream(uri, new ByteArrayInputStream(dados));
        return uri;
    }

    private ContentResolver cr() {
        return RuntimeEnvironment.getApplication().getContentResolver();
    }

    @Test
    public void textoAgendado() throws Exception {
        responder("{\"id\":\"111_222\"}");
        String id = new Graph("111", "TOKEN").publicarTexto("Olá ❤️", 1_900_000_000L);
        assertEquals("111_222", id);
        Pedido p = pedidos.get(0);
        assertEquals("POST", p.metodo);
        assertEquals("/111/feed", p.caminho);
        Map<String, String> f = p.form();
        assertEquals("Olá ❤️", f.get("message"));
        assertEquals("false", f.get("published"));
        assertEquals("1900000000", f.get("scheduled_publish_time"));
        assertEquals("TOKEN", f.get("access_token"));
    }

    @Test
    public void umaFotoEmMultipart() throws Exception {
        responder("{\"id\":\"9\",\"post_id\":\"111_9\"}");
        byte[] img = {(byte) 0x89, 'P', 'N', 'G', 1, 2, 3};
        String id = new Graph("111", "T").publicarFoto(cr(), arquivo("a.png", img), "Legenda", null);
        assertEquals("111_9", id);
        Pedido p = pedidos.get(0);
        assertEquals("/111/photos", p.caminho);
        assertTrue(p.cabecalhos.get("content-type").startsWith("multipart/form-data; boundary="));
        String corpo = p.corpoTexto();
        assertTrue(corpo.contains("name=\"caption\"\r\n\r\nLegenda\r\n"));
        assertTrue(corpo.contains("name=\"access_token\"\r\n\r\nT\r\n"));
        assertTrue(corpo.contains(new String(img, StandardCharsets.ISO_8859_1)));
    }

    @Test
    public void variasFotosAgendadas() throws Exception {
        responder("{\"id\":\"f1\"}");
        responder("{\"id\":\"f2\"}");
        responder("{\"id\":\"111_post\"}");
        List<String> progresso = new ArrayList<>();
        String id = new Graph("111", "T").publicarFotos(cr(),
                Arrays.asList(arquivo("1.jpg", new byte[]{1}), arquivo("2.jpg", new byte[]{2})),
                "Álbum", 1_900_000_000L, progresso::add);
        assertEquals("111_post", id);
        assertTrue(pedidos.get(0).corpoTexto().contains("name=\"published\"\r\n\r\nfalse"));
        assertTrue(pedidos.get(0).corpoTexto().contains("name=\"temporary\"\r\n\r\ntrue"));
        Map<String, String> feed = pedidos.get(2).form();
        assertEquals("/111/feed", pedidos.get(2).caminho);
        assertEquals("{\"media_fbid\":\"f1\"}", feed.get("attached_media[0]"));
        assertEquals("{\"media_fbid\":\"f2\"}", feed.get("attached_media[1]"));
        assertEquals("1900000000", feed.get("scheduled_publish_time"));
        assertEquals("Enviando foto 1 de 2...", progresso.get(0));
    }

    @Test
    public void reelCompleto() throws Exception {
        responder("{\"video_id\":\"v1\",\"upload_url\":\"$BASEupload/v1\"}");
        responder("{\"success\":true}");
        responder("{\"success\":true}");
        byte[] video = new byte[300_000];
        for (int i = 0; i < video.length; i++) video[i] = (byte) i;
        List<String> progresso = new ArrayList<>();
        String id = new Graph("111", "TOK").publicarReel(cr(), arquivo("v.mp4", video),
                "Meu reel #reels", 1_900_000_000L, progresso::add);
        assertEquals("v1", id);

        assertEquals("start", pedidos.get(0).form().get("upload_phase"));
        Pedido envio = pedidos.get(1);
        assertEquals("/upload/v1", envio.caminho);
        assertEquals("OAuth TOK", envio.cabecalhos.get("authorization"));
        assertEquals("0", envio.cabecalhos.get("offset"));
        assertEquals("300000", envio.cabecalhos.get("file_size"));
        assertArrayEquals(video, envio.corpo);

        Map<String, String> fim = pedidos.get(2).form();
        assertEquals("finish", fim.get("upload_phase"));
        assertEquals("v1", fim.get("video_id"));
        assertEquals("SCHEDULED", fim.get("video_state"));
        assertEquals("1900000000", fim.get("scheduled_publish_time"));
        assertEquals("Meu reel #reels", fim.get("description"));
        assertTrue(progresso.contains("Enviando vídeo (0.3 MB): 100%"));
    }

    @Test
    public void erroDeTokenViraMensagemClara() {
        respostas.add(new String[]{"400",
                "{\"error\":{\"message\":\"Session has expired\",\"code\":190}}"});
        try {
            new Graph("111", "T").publicarTexto("x", null);
            fail("deveria dar erro");
        } catch (Graph.ErroFacebook e) {
            assertTrue(e.getMessage().contains("(190)"));
            assertTrue(e.getMessage().contains("Conecte a Página de novo"));
        }
    }

    @Test
    public void conectarTrocaTokenEListaPaginas() throws Exception {
        responder("{\"access_token\":\"LONGO\"}");
        responder("{\"data\":[{\"id\":\"1\",\"name\":\"Meu Amor\",\"access_token\":\"PT\"}]}");
        assertEquals("LONGO", Graph.tokenLongo("APP", "SEGREDO", "CURTO"));
        assertEquals("PT", Graph.paginas("LONGO").getJSONObject(0).getString("access_token"));
        assertEquals("/oauth/access_token", pedidos.get(0).caminho);
        assertTrue(pedidos.get(0).query.contains("grant_type=fb_exchange_token"));
        assertTrue(pedidos.get(0).query.contains("fb_exchange_token=CURTO"));
        assertTrue(pedidos.get(1).query.contains("access_token=LONGO"));
    }
}
