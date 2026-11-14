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

    private ServidorFalso srv;
    private List<ServidorFalso.Pedido> pedidos;
    private LinkedList<String[]> respostas;
    private String base;

    @Before
    public void iniciar() throws Exception {
        srv = new ServidorFalso();
        pedidos = srv.pedidos;
        respostas = srv.respostas;
        base = srv.base;
    }

    @After
    public void parar() throws Exception {
        srv.parar();
    }

    private void responder(String json) { srv.responder(json); }

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
        ServidorFalso.Pedido p = pedidos.get(0);
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
        ServidorFalso.Pedido p = pedidos.get(0);
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
        ServidorFalso.Pedido envio = pedidos.get(1);
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
