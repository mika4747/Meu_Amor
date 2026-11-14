package com.meuamor.postador;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedList;
import java.util.List;
import java.util.Map;

/** "Facebook" falso para os testes: servidor HTTP local que guarda cada requisição
 *  e responde com os JSONs enfileirados (aponta Graph.BASE para ele). */
class ServidorFalso {

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
    final List<Pedido> pedidos = new ArrayList<>();
    final LinkedList<String[]> respostas = new LinkedList<>(); // {status, json}
    String base;

    ServidorFalso() throws Exception {
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

    void parar() throws Exception {
        servidor.close();
        atendente.join(2000);
    }

    void responder(String json) { respostas.add(new String[]{"200", json}); }
    void responder(int status, String json) { respostas.add(new String[]{String.valueOf(status), json}); }
}
