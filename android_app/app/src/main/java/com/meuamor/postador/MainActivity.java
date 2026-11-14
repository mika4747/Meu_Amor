package com.meuamor.postador;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.DatePickerDialog;
import android.app.TimePickerDialog;
import android.content.ClipData;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.ProgressBar;
import android.widget.RadioGroup;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.time.DayOfWeek;
import java.time.Instant;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.EnumSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

public class MainActivity extends Activity {

    private static final int PEDIR_FOTOS = 1;
    private static final int PEDIR_VIDEO = 2;
    private static final Locale PT = new Locale("pt", "BR");
    private static final DateTimeFormatter FORMATO =
            DateTimeFormatter.ofPattern("EEE, dd/MM 'às' HH:mm", PT);

    private Dados dados;

    // mídia escolhida
    private final List<Uri> fotos = new ArrayList<>();
    private Uri reel;
    // horário escolhido manualmente (segundos Unix)
    private Long horarioEscolhido;
    // Reels do último envio: {nome da Página, id do vídeo, token da Página}
    private final List<String[]> ultimosReels = new ArrayList<>();
    private boolean enviando;

    private View painelPostar, painelAgenda, painelConta;
    private Button abaPostar, abaAgenda, abaConta;
    private TextView txtPagina, txtMidia, txtQuando, txtPrevia, txtResultado;
    private TextView txtProximos, txtHistorico, txtContaStatus, txtContaResultado;
    private EditText edtLegenda, edtHashtagsPost, edtHorarios, edtHashtagsPadrao, edtAssinatura;
    private EditText edtAppId, edtAppSecret, edtToken;
    private RadioGroup rgQuando;
    private android.widget.LinearLayout listaPaginas;
    private Button btnEnviar, btnStatusReel, btnConectar;
    private ProgressBar progresso;
    private final CheckBox[] dias = new CheckBox[7];

    @Override
    protected void onCreate(Bundle estado) {
        super.onCreate(estado);
        setContentView(R.layout.activity_main);
        dados = new Dados(this);
        ligarViews();
        carregarAgenda();
        atualizarCabecalho();
        montarListaPaginas();
        atualizarMidia();
        atualizarQuando();
        atualizarPrevia();
        mostrarAba(dados.conectado() ? 0 : 2);
        receberCompartilhamento(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        receberCompartilhamento(intent);
    }

    // =================================================================== montagem

    private void ligarViews() {
        painelPostar = findViewById(R.id.painelPostar);
        painelAgenda = findViewById(R.id.painelAgenda);
        painelConta = findViewById(R.id.painelConta);
        abaPostar = findViewById(R.id.abaPostar);
        abaAgenda = findViewById(R.id.abaAgenda);
        abaConta = findViewById(R.id.abaConta);
        txtPagina = findViewById(R.id.txtPagina);
        txtMidia = findViewById(R.id.txtMidia);
        txtQuando = findViewById(R.id.txtQuando);
        txtPrevia = findViewById(R.id.txtPrevia);
        txtResultado = findViewById(R.id.txtResultado);
        txtProximos = findViewById(R.id.txtProximos);
        txtHistorico = findViewById(R.id.txtHistorico);
        txtContaStatus = findViewById(R.id.txtContaStatus);
        txtContaResultado = findViewById(R.id.txtContaResultado);
        edtLegenda = findViewById(R.id.edtLegenda);
        edtHashtagsPost = findViewById(R.id.edtHashtagsPost);
        edtHorarios = findViewById(R.id.edtHorarios);
        edtHashtagsPadrao = findViewById(R.id.edtHashtagsPadrao);
        edtAssinatura = findViewById(R.id.edtAssinatura);
        edtAppId = findViewById(R.id.edtAppId);
        edtAppSecret = findViewById(R.id.edtAppSecret);
        edtToken = findViewById(R.id.edtToken);
        rgQuando = findViewById(R.id.rgQuando);
        listaPaginas = findViewById(R.id.listaPaginas);
        btnEnviar = findViewById(R.id.btnEnviar);
        btnStatusReel = findViewById(R.id.btnStatusReel);
        btnConectar = findViewById(R.id.btnConectar);
        progresso = findViewById(R.id.progresso);
        int[] ids = {R.id.dia1, R.id.dia2, R.id.dia3, R.id.dia4, R.id.dia5, R.id.dia6, R.id.dia7};
        for (int i = 0; i < 7; i++) dias[i] = findViewById(ids[i]);

        abaPostar.setOnClickListener(v -> mostrarAba(0));
        abaAgenda.setOnClickListener(v -> mostrarAba(1));
        abaConta.setOnClickListener(v -> mostrarAba(2));

        findViewById(R.id.btnFotos).setOnClickListener(v -> escolher("image/*", true, PEDIR_FOTOS));
        findViewById(R.id.btnReel).setOnClickListener(v -> escolher("video/*", false, PEDIR_VIDEO));
        findViewById(R.id.btnLimparMidia).setOnClickListener(v -> {
            fotos.clear();
            reel = null;
            atualizarMidia();
        });

        TextWatcher aoDigitar = new TextWatcher() {
            public void beforeTextChanged(CharSequence s, int a, int b, int c) {}
            public void onTextChanged(CharSequence s, int a, int b, int c) {}
            public void afterTextChanged(Editable s) { atualizarPrevia(); }
        };
        edtLegenda.addTextChangedListener(aoDigitar);
        edtHashtagsPost.addTextChangedListener(aoDigitar);

        rgQuando.setOnCheckedChangeListener((g, id) -> {
            if (id == R.id.rbEscolher && horarioEscolhido == null) escolherDataHora();
            atualizarQuando();
        });
        txtQuando.setOnClickListener(v -> {
            if (rgQuando.getCheckedRadioButtonId() == R.id.rbEscolher) escolherDataHora();
        });

        btnEnviar.setOnClickListener(v -> enviar());
        btnStatusReel.setOnClickListener(v -> verStatusReel());

        findViewById(R.id.btnSalvarAgenda).setOnClickListener(v -> salvarAgenda());
        findViewById(R.id.btnLimparHistorico).setOnClickListener(v ->
                new AlertDialog.Builder(this)
                        .setMessage("Apagar a lista de posts enviados? (Os posts no Facebook "
                                + "não são apagados.)")
                        .setPositiveButton("Apagar", (d, w) -> {
                            dados.limparHistorico();
                            atualizarHistorico();
                        })
                        .setNegativeButton("Cancelar", null).show());

        findViewById(R.id.btnAbrirApps).setOnClickListener(v ->
                abrirSite("https://developers.facebook.com/apps"));
        findViewById(R.id.btnAbrirExplorer).setOnClickListener(v ->
                abrirSite("https://developers.facebook.com/tools/explorer"));
        btnConectar.setOnClickListener(v -> conectar());
        findViewById(R.id.btnVerificar).setOnClickListener(v -> verificar());
        findViewById(R.id.btnDesconectar).setOnClickListener(v ->
                new AlertDialog.Builder(this)
                        .setMessage("Desconectar todas as Páginas deste celular?")
                        .setPositiveButton("Desconectar", (d, w) -> {
                            dados.desconectar();
                            atualizarCabecalho();
                            montarListaPaginas();
                        })
                        .setNegativeButton("Cancelar", null).show());

        edtAppId.setText(dados.appId());
        // campos de senha usam fonte monoespaçada por padrão; deixa igual aos outros
        edtAppSecret.setTypeface(android.graphics.Typeface.DEFAULT);
        edtToken.setTypeface(android.graphics.Typeface.DEFAULT);
    }

    private void mostrarAba(int aba) {
        painelPostar.setVisibility(aba == 0 ? View.VISIBLE : View.GONE);
        painelAgenda.setVisibility(aba == 1 ? View.VISIBLE : View.GONE);
        painelConta.setVisibility(aba == 2 ? View.VISIBLE : View.GONE);
        Button[] abas = {abaPostar, abaAgenda, abaConta};
        for (int i = 0; i < 3; i++) {
            abas[i].setAlpha(i == aba ? 1f : 0.6f);
            abas[i].setPaintFlags(i == aba
                    ? abas[i].getPaintFlags() | android.graphics.Paint.UNDERLINE_TEXT_FLAG
                    : abas[i].getPaintFlags() & ~android.graphics.Paint.UNDERLINE_TEXT_FLAG);
        }
        if (aba == 0) atualizarQuando();
        if (aba == 1) {
            atualizarProximos();
            atualizarHistorico();
        }
        ((ScrollView) findViewById(R.id.rolagem)).scrollTo(0, 0);
    }

    private void atualizarCabecalho() {
        JSONArray ps = dados.paginas();
        if (ps.length() > 0) {
            List<JSONObject> lista = new ArrayList<>();
            for (int i = 0; i < ps.length(); i++) lista.add(ps.optJSONObject(i));
            String todas = nomes(lista);
            txtPagina.setText((ps.length() == 1 ? "Página: " : ps.length() + " Páginas: ") + todas);
            txtContaStatus.setText("✅ Conectado a: " + todas);
        } else {
            txtPagina.setText("Nenhuma Página conectada");
            txtContaStatus.setText("Conectar suas Páginas do Facebook");
        }
    }

    // =================================================================== mídia

    private void escolher(String tipo, boolean varios, int pedido) {
        Intent i = new Intent(Intent.ACTION_GET_CONTENT);
        i.setType(tipo);
        i.addCategory(Intent.CATEGORY_OPENABLE);
        i.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, varios);
        try {
            startActivityForResult(Intent.createChooser(i, varios ? "Escolha as fotos"
                    : "Escolha o vídeo"), pedido);
        } catch (android.content.ActivityNotFoundException e) {
            aviso("Nenhum app de galeria encontrado.");
        }
    }

    @Override
    protected void onActivityResult(int pedido, int resultado, Intent data) {
        super.onActivityResult(pedido, resultado, data);
        if (resultado != RESULT_OK || data == null) return;
        List<Uri> uris = new ArrayList<>();
        ClipData clip = data.getClipData();
        if (clip != null) {
            for (int i = 0; i < clip.getItemCount(); i++) uris.add(clip.getItemAt(i).getUri());
        } else if (data.getData() != null) {
            uris.add(data.getData());
        }
        if (uris.isEmpty()) return;
        if (pedido == PEDIR_FOTOS) {
            reel = null;
            fotos.addAll(uris);
        } else {
            fotos.clear();
            reel = uris.get(0);
        }
        atualizarMidia();
    }

    private void receberCompartilhamento(Intent intent) {
        if (intent == null) return;
        String acao = intent.getAction();
        if (!Intent.ACTION_SEND.equals(acao) && !Intent.ACTION_SEND_MULTIPLE.equals(acao)) return;
        List<Uri> uris = new ArrayList<>();
        if (Intent.ACTION_SEND.equals(acao)) {
            Uri u = intent.getParcelableExtra(Intent.EXTRA_STREAM);
            if (u != null) uris.add(u);
        } else {
            ArrayList<Uri> lista = intent.getParcelableArrayListExtra(Intent.EXTRA_STREAM);
            if (lista != null) uris.addAll(lista);
        }
        if (uris.isEmpty()) return;
        String tipo = getContentResolver().getType(uris.get(0));
        if (tipo == null) tipo = intent.getType() == null ? "" : intent.getType();
        fotos.clear();
        reel = null;
        if (tipo.startsWith("video")) {
            reel = uris.get(0);
        } else {
            fotos.addAll(uris);
        }
        String texto = intent.getStringExtra(Intent.EXTRA_TEXT);
        if (texto != null && edtLegenda.getText().length() == 0) edtLegenda.setText(texto);
        atualizarMidia();
        mostrarAba(0);
    }

    private void atualizarMidia() {
        if (reel != null) {
            long t = Graph.tamanho(getContentResolver(), reel);
            txtMidia.setText("🎬 Reel escolhido" + (t > 0
                    ? String.format(Locale.ROOT, " (%.1f MB)", t / 1e6) : "")
                    + "\nVídeo vertical 9:16, de 3 a 90 segundos.");
        } else if (fotos.size() == 1) {
            txtMidia.setText("📷 1 foto escolhida");
        } else if (fotos.size() > 1) {
            txtMidia.setText("📷 " + fotos.size() + " fotos escolhidas (saem juntas num só post)");
        } else {
            txtMidia.setText("Nenhuma mídia: o post será só de texto.");
        }
    }

    // =================================================================== quando

    private ZoneId fuso() { return ZoneId.systemDefault(); }

    private long agoraS() { return System.currentTimeMillis() / 1000; }

    private ZonedDateTime proximoLivre() {
        List<LocalTime> hs;
        try {
            hs = Legenda.horarios(dados.horarios());
        } catch (IllegalArgumentException e) {
            return null;
        }
        if (hs.isEmpty()) return null;
        return Legenda.proximoLivre(hs, dados.dias(), dados.ocupados(agoraS()),
                ZonedDateTime.now(fuso()));
    }

    private String formatar(long segundos) {
        return FORMATO.format(Instant.ofEpochSecond(segundos).atZone(fuso()));
    }

    private void atualizarQuando() {
        int id = rgQuando.getCheckedRadioButtonId();
        if (id == R.id.rbAgora) {
            txtQuando.setText("Publica assim que você tocar no botão.");
            btnEnviar.setText("Publicar agora");
        } else if (id == R.id.rbEscolher) {
            txtQuando.setText(horarioEscolhido == null ? "Toque aqui para escolher dia e hora."
                    : formatar(horarioEscolhido) + "  (toque para mudar)");
            btnEnviar.setText("Agendar");
        } else {
            ZonedDateTime p = proximoLivre();
            txtQuando.setText(p == null
                    ? "Nenhum horário livre nos próximos 30 dias. Veja a aba Horários."
                    : FORMATO.format(p));
            btnEnviar.setText("Agendar");
        }
    }

    private void escolherDataHora() {
        ZonedDateTime base = horarioEscolhido != null
                ? Instant.ofEpochSecond(horarioEscolhido).atZone(fuso())
                : ZonedDateTime.now(fuso()).plusHours(1);
        new DatePickerDialog(this, (dp, ano, mes, dia) ->
                new TimePickerDialog(this, (tp, hora, minuto) -> {
                    ZonedDateTime escolhido = ZonedDateTime.of(ano, mes + 1, dia, hora, minuto,
                            0, 0, fuso());
                    String problema = Legenda.problemaNoHorario(escolhido.toEpochSecond(), agoraS());
                    if (problema != null) {
                        aviso(problema);
                        return;
                    }
                    horarioEscolhido = escolhido.toEpochSecond();
                    atualizarQuando();
                }, base.getHour(), base.getMinute(), true).show(),
                base.getYear(), base.getMonthValue() - 1, base.getDayOfMonth()).show();
    }

    // =================================================================== legenda

    private String legendaFinal() {
        return Legenda.montar(edtLegenda.getText().toString(), dados.assinatura(),
                Legenda.hashtags(dados.hashtags(), edtHashtagsPost.getText().toString()));
    }

    private void atualizarPrevia() {
        String l = legendaFinal();
        txtPrevia.setText(l.isEmpty() ? "(vazia)" : l);
    }

    // =================================================================== Páginas

    /** Monta uma caixinha por Página conectada na aba Postar. */
    private void montarListaPaginas() {
        listaPaginas.removeAllViews();
        JSONArray ps = dados.paginas();
        if (ps.length() == 0) {
            TextView t = new TextView(this);
            t.setText("Nenhuma Página conectada. Conecte na aba Conta.");
            t.setTextColor(getColor(R.color.texto_suave));
            listaPaginas.addView(t);
            return;
        }
        Set<String> marcadas = dados.selecionadas();
        for (int i = 0; i < ps.length(); i++) {
            JSONObject p = ps.optJSONObject(i);
            CheckBox cb = new CheckBox(this);
            cb.setText(p.optString("nome"));
            cb.setTag(p.optString("id"));
            cb.setTextSize(16);
            cb.setChecked(marcadas.contains(p.optString("id")));
            cb.setOnCheckedChangeListener((b, marcada) -> {
                Set<String> s = dados.selecionadas();
                if (marcada) s.add((String) b.getTag()); else s.remove(b.getTag());
                dados.salvarSelecionadas(s);
            });
            listaPaginas.addView(cb);
        }
    }

    /** Páginas marcadas, na ordem em que foram conectadas. */
    private List<JSONObject> paginasMarcadas() {
        List<JSONObject> lista = new ArrayList<>();
        Set<String> marcadas = dados.selecionadas();
        JSONArray ps = dados.paginas();
        for (int i = 0; i < ps.length(); i++) {
            if (marcadas.contains(ps.optJSONObject(i).optString("id"))) {
                lista.add(ps.optJSONObject(i));
            }
        }
        return lista;
    }

    private void marcarSomente(Set<String> ids) {
        dados.salvarSelecionadas(ids);
        montarListaPaginas();
    }

    private static String nomes(List<JSONObject> paginas) {
        StringBuilder sb = new StringBuilder();
        for (JSONObject p : paginas) {
            if (sb.length() > 0) sb.append(", ");
            sb.append(p.optString("nome"));
        }
        return sb.toString();
    }

    // =================================================================== enviar

    private void enviar() {
        if (enviando) return;
        if (!dados.conectado()) {
            aviso("Conecte suas Páginas primeiro, na aba Conta.");
            mostrarAba(2);
            return;
        }
        final List<JSONObject> alvos = paginasMarcadas();
        if (alvos.isEmpty()) {
            aviso("Marque pelo menos uma Página em \"Publicar em\".");
            return;
        }
        final String legenda = legendaFinal();
        if (legenda.isEmpty() && fotos.isEmpty() && reel == null) {
            aviso("Escreva uma legenda ou escolha uma foto ou vídeo.");
            return;
        }

        Long quando;
        int id = rgQuando.getCheckedRadioButtonId();
        if (id == R.id.rbAgora) {
            quando = null;
        } else if (id == R.id.rbEscolher) {
            if (horarioEscolhido == null) {
                escolherDataHora();
                return;
            }
            quando = horarioEscolhido;
        } else {
            ZonedDateTime p = proximoLivre();
            if (p == null) {
                aviso("Nenhum horário livre nos próximos 30 dias. Ajuste na aba Horários.");
                return;
            }
            quando = p.toEpochSecond();
        }
        if (quando != null) {
            String problema = Legenda.problemaNoHorario(quando, agoraS());
            if (problema != null) {
                aviso(problema);
                return;
            }
        }

        final String tipo = reel != null ? "Reel" : fotos.size() > 1 ? fotos.size() + " fotos"
                : fotos.size() == 1 ? "Foto" : "Texto";
        String quandoTexto = quando == null ? "agora" : formatar(quando);
        new AlertDialog.Builder(this)
                .setTitle(quando == null ? "Publicar agora?" : "Agendar?")
                .setMessage(tipo + " • " + quandoTexto + "\nEm: " + nomes(alvos)
                        + "\n\n" + legenda)
                .setPositiveButton(quando == null ? "Publicar" : "Agendar",
                        (d, w) -> executarEnvio(tipo, legenda, quando, alvos))
                .setNegativeButton("Voltar", null)
                .show();
    }

    /** Resultado do envio para uma Página: id do post ou mensagem de erro. */
    private static class Resultado {
        final JSONObject pagina;
        final String id, erro;

        Resultado(JSONObject pagina, String id, String erro) {
            this.pagina = pagina;
            this.id = id;
            this.erro = erro;
        }
    }

    private void executarEnvio(String tipo, String legenda, Long quando, List<JSONObject> alvos) {
        enviando = true;
        btnEnviar.setEnabled(false);
        btnStatusReel.setVisibility(View.GONE);
        progresso.setVisibility(View.VISIBLE);
        txtResultado.setText("Enviando...");
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        final List<Uri> minhasFotos = new ArrayList<>(fotos);
        final Uri meuReel = reel;

        new Thread(() -> {
            List<Resultado> resultados = new ArrayList<>();
            for (JSONObject pagina : alvos) {
                final String prefixo = alvos.size() > 1 ? pagina.optString("nome") + ": " : "";
                Graph graph = new Graph(pagina.optString("id"), pagina.optString("token"));
                Graph.Progresso p = msg -> runOnUiThread(() -> txtResultado.setText(prefixo + msg));
                String id = null, erro = null;
                try {
                    if (meuReel != null) {
                        id = graph.publicarReel(getContentResolver(), meuReel, legenda, quando, p);
                    } else if (minhasFotos.size() > 1) {
                        id = graph.publicarFotos(getContentResolver(), minhasFotos, legenda,
                                quando, p);
                    } else if (minhasFotos.size() == 1) {
                        p.mostrar("Enviando foto...");
                        id = graph.publicarFoto(getContentResolver(), minhasFotos.get(0),
                                legenda, quando);
                    } else {
                        p.mostrar("Enviando...");
                        id = graph.publicarTexto(legenda, quando);
                    }
                } catch (Graph.ErroFacebook e) {
                    erro = e.getMessage();
                } catch (RuntimeException e) {
                    erro = "Erro inesperado: " + e;
                }
                resultados.add(new Resultado(pagina, id, erro));
            }
            runOnUiThread(() -> terminarEnvio(tipo, legenda, quando, resultados, meuReel != null));
        }).start();
    }

    private void terminarEnvio(String tipo, String legenda, Long quando,
                               List<Resultado> resultados, boolean foiReel) {
        enviando = false;
        btnEnviar.setEnabled(true);
        progresso.setVisibility(View.GONE);
        getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        String resumo = legenda.length() > 60 ? legenda.substring(0, 60) + "…" : legenda;
        StringBuilder msg = new StringBuilder();
        StringBuilder erros = new StringBuilder();
        Set<String> falharam = new java.util.HashSet<>();
        if (foiReel) ultimosReels.clear();
        for (Resultado r : resultados) {
            String nome = r.pagina.optString("nome");
            if (r.erro == null) {
                dados.registrar(quando == null ? 0 : quando, tipo, resumo.replace('\n', ' '),
                        r.id, nome);
                msg.append("✅ ").append(nome).append(": ")
                        .append(quando == null ? "publicado" : "agendado").append("\n");
                if (foiReel) {
                    ultimosReels.add(new String[]{nome, r.id, r.pagina.optString("token")});
                }
            } else {
                falharam.add(r.pagina.optString("id"));
                msg.append("❌ ").append(nome).append(": ").append(r.erro).append("\n");
                erros.append(nome).append(":\n").append(r.erro).append("\n\n");
            }
        }
        boolean algumOk = falharam.size() < resultados.size();
        if (quando != null && algumOk) msg.insert(0, "Agendado para " + formatar(quando) + "\n");
        if (foiReel && algumOk) {
            msg.append("\nO Facebook leva alguns minutos para processar o vídeo.");
            btnStatusReel.setVisibility(View.VISIBLE);
        }
        txtResultado.setText(msg.toString().trim());

        if (!falharam.isEmpty()) {
            if (algumOk) {
                // Deixa marcadas só as Páginas que falharam e fixa o mesmo horário,
                // para "tentar de novo" não duplicar nas que já deram certo.
                marcarSomente(falharam);
                if (quando != null) {
                    horarioEscolhido = quando;
                    rgQuando.check(R.id.rbEscolher);
                }
                atualizarQuando();
                erros.append("Deixei marcadas só as Páginas que falharam: toque no botão de "
                        + "novo para tentar só nelas.");
            }
            new AlertDialog.Builder(this)
                    .setTitle(algumOk ? "Algumas Páginas falharam" : "Não deu certo")
                    .setMessage(erros.toString().trim())
                    .setPositiveButton("OK", null).show();
            return;
        }
        Toast.makeText(this, quando == null ? "Publicado!" : "Agendado!", Toast.LENGTH_SHORT).show();

        // prepara o próximo post
        fotos.clear();
        reel = null;
        edtLegenda.setText("");
        edtHashtagsPost.setText("");
        horarioEscolhido = null;
        atualizarMidia();
        atualizarQuando();
    }

    private void verStatusReel() {
        if (ultimosReels.isEmpty()) return;
        final List<String[]> reels = new ArrayList<>(ultimosReels);
        txtResultado.setText("Consultando o Reel...");
        new Thread(() -> {
            StringBuilder sb = new StringBuilder();
            for (String[] r : reels) {
                String msg;
                try {
                    // o id do vídeo vale para a Graph API com o token da Página dele
                    String st = new Graph("", r[2]).statusVideo(r[1]);
                    switch (st) {
                        case "ready": msg = "✅ processado e pronto."; break;
                        case "processing": msg = "⏳ o Facebook ainda está processando."; break;
                        case "upload_complete": msg = "⏳ recebido, aguardando processamento."; break;
                        case "error": msg = "❌ o Facebook recusou o vídeo. Confira se é vertical "
                                + "9:16 e tem de 3 a 90 segundos."; break;
                        default: msg = "situação: " + st;
                    }
                } catch (Graph.ErroFacebook e) {
                    msg = "❌ " + e.getMessage();
                }
                if (sb.length() > 0) sb.append("\n");
                sb.append(reels.size() > 1 ? r[0] + ": " : "Reel: ").append(msg);
            }
            final String m = sb.toString();
            runOnUiThread(() -> txtResultado.setText(m));
        }).start();
    }

    // =================================================================== horários

    private void carregarAgenda() {
        edtHorarios.setText(dados.horarios());
        edtHashtagsPadrao.setText(dados.hashtags());
        edtAssinatura.setText(dados.assinatura());
        Set<DayOfWeek> ds = dados.dias();
        for (int i = 0; i < 7; i++) dias[i].setChecked(ds.contains(DayOfWeek.of(i + 1)));
    }

    private void salvarAgenda() {
        List<LocalTime> hs;
        try {
            hs = Legenda.horarios(edtHorarios.getText().toString());
        } catch (IllegalArgumentException e) {
            aviso(e.getMessage());
            return;
        }
        if (hs.isEmpty()) {
            aviso("Informe pelo menos um horário.");
            return;
        }
        Set<DayOfWeek> ds = EnumSet.noneOf(DayOfWeek.class);
        for (int i = 0; i < 7; i++) if (dias[i].isChecked()) ds.add(DayOfWeek.of(i + 1));
        if (ds.isEmpty()) {
            aviso("Marque pelo menos um dia da semana.");
            return;
        }
        StringBuilder texto = new StringBuilder();
        for (LocalTime h : hs) {
            if (texto.length() > 0) texto.append(", ");
            texto.append(h.toString());
        }
        String tags = String.join(" ", Legenda.hashtags(edtHashtagsPadrao.getText().toString()));
        dados.salvarCalendario(texto.toString(), ds, tags, edtAssinatura.getText().toString().trim());
        carregarAgenda();
        atualizarProximos();
        atualizarPrevia();
        Toast.makeText(this, "Horários salvos", Toast.LENGTH_SHORT).show();
    }

    private void atualizarProximos() {
        List<LocalTime> hs;
        try {
            hs = Legenda.horarios(dados.horarios());
        } catch (IllegalArgumentException e) {
            txtProximos.setText(e.getMessage());
            return;
        }
        Set<Long> ocupados = dados.ocupados(agoraS());
        StringBuilder sb = new StringBuilder("Próximos horários livres:");
        ZonedDateTime agora = ZonedDateTime.now(fuso());
        for (int i = 0; i < 4; i++) {
            ZonedDateTime p = Legenda.proximoLivre(hs, dados.dias(), ocupados, agora);
            if (p == null) break;
            sb.append("\n• ").append(FORMATO.format(p));
            ocupados.add(p.toEpochSecond());
        }
        txtProximos.setText(sb);
    }

    private void atualizarHistorico() {
        JSONArray h = dados.historico();
        if (h.length() == 0) {
            txtHistorico.setText("Nenhum post enviado ainda.");
            return;
        }
        StringBuilder sb = new StringBuilder();
        long agora = agoraS();
        for (int i = h.length() - 1; i >= 0 && i >= h.length() - 30; i--) {
            JSONObject item = h.optJSONObject(i);
            if (item == null) continue;
            long q = item.optLong("quando");
            String situacao = q == 0 ? "publicado " + formatar(item.optLong("enviado"))
                    : (q > agora ? "⏰ agendado " : "✅ saiu ") + formatar(q);
            if (sb.length() > 0) sb.append("\n\n");
            String pagina = item.optString("pagina", "");
            if (!pagina.isEmpty()) sb.append(pagina).append(" • ");
            sb.append(item.optString("tipo")).append(" • ").append(situacao)
                    .append("\n").append(item.optString("resumo"));
        }
        txtHistorico.setText(sb);
    }

    // =================================================================== conta

    private void conectar() {
        final String appId = edtAppId.getText().toString().trim();
        final String secret = edtAppSecret.getText().toString().trim();
        final String token = edtToken.getText().toString().trim();
        if (appId.isEmpty() || secret.isEmpty() || token.isEmpty()) {
            aviso("Preencha o App ID, o App Secret e o token.");
            return;
        }
        dados.salvarAppId(appId);
        btnConectar.setEnabled(false);
        txtContaResultado.setText("Conectando...");
        new Thread(() -> {
            try {
                String longo = Graph.tokenLongo(appId, secret, token);
                JSONArray paginas = Graph.paginas(longo);
                runOnUiThread(() -> finalizarConexao(paginas, appId, secret));
            } catch (Graph.ErroFacebook e) {
                runOnUiThread(() -> {
                    btnConectar.setEnabled(true);
                    txtContaResultado.setText("❌ " + e.getMessage());
                });
            }
        }).start();
    }

    /** Guarda todas as Páginas autorizadas (cada uma com seu token) e confere os tokens. */
    private void finalizarConexao(JSONArray encontradas, String appId, String secret) {
        if (encontradas.length() == 0) {
            btnConectar.setEnabled(true);
            txtContaResultado.setText("❌ Nenhuma Página encontrada. Gere o token de novo e, na "
                    + "janela do Facebook, marque as suas Páginas e as 3 permissões.");
            return;
        }
        final JSONArray paginas = new JSONArray();
        for (int i = 0; i < encontradas.length(); i++) {
            JSONObject e = encontradas.optJSONObject(i);
            try {
                JSONObject p = new JSONObject();
                p.put("id", e.optString("id"));
                p.put("nome", e.optString("name"));
                p.put("token", e.optString("access_token"));
                paginas.put(p);
            } catch (org.json.JSONException ignorado) {
            }
        }
        dados.salvarPaginas(paginas);
        edtAppSecret.setText("");
        edtToken.setText("");
        atualizarCabecalho();
        montarListaPaginas();
        txtContaResultado.setText("✅ " + paginas.length() + " Página(s) conectada(s). "
                + "Conferindo os tokens...");
        new Thread(() -> {
            StringBuilder sb = new StringBuilder();
            boolean algumExpira = false;
            for (int i = 0; i < paginas.length(); i++) {
                JSONObject p = paginas.optJSONObject(i);
                sb.append("\n• ").append(p.optString("nome"));
                try {
                    JSONObject info = Graph.depurarToken(p.optString("token"), appId, secret);
                    long expira = info.optLong("expires_at", -1);
                    JSONArray escopos = info.optJSONArray("scopes");
                    List<String> faltando = new ArrayList<>();
                    for (String perm : Graph.PERMISSOES) {
                        boolean tem = false;
                        for (int j = 0; escopos != null && j < escopos.length(); j++) {
                            if (perm.equals(escopos.optString(j))) tem = true;
                        }
                        if (!tem) faltando.add(perm);
                    }
                    if (expira > 0) {
                        algumExpira = true;
                        sb.append("\n   ⚠️ o token expira em ").append(formatar(expira))
                                .append(". Conecte de novo antes disso.");
                    }
                    if (!faltando.isEmpty()) {
                        sb.append("\n   ⚠️ faltam as permissões: ").append(String.join(", ", faltando))
                                .append(". Gere o token de novo marcando essas permissões.");
                    }
                } catch (Graph.ErroFacebook e) {
                    sb.append("\n   (não foi possível conferir o token: ").append(e.getMessage())
                            .append(")");
                }
            }
            final String lista = sb.toString();
            final boolean expira = algumExpira;
            runOnUiThread(() -> {
                btnConectar.setEnabled(true);
                txtContaResultado.setText("✅ " + paginas.length() + " Página(s) conectada(s):"
                        + lista + (expira ? "" : "\n\nOs tokens das Páginas não expiram."));
                Toast.makeText(this, "Páginas conectadas!", Toast.LENGTH_SHORT).show();
            });
        }).start();
    }

    private void verificar() {
        if (!dados.conectado()) {
            aviso("Nenhuma Página conectada.");
            return;
        }
        final JSONArray paginas = dados.paginas();
        txtContaResultado.setText("Testando...");
        new Thread(() -> {
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < paginas.length(); i++) {
                JSONObject p = paginas.optJSONObject(i);
                if (sb.length() > 0) sb.append("\n");
                try {
                    new Graph(p.optString("id"), p.optString("token")).verificar();
                    sb.append("✅ ").append(p.optString("nome")).append(": funcionando");
                } catch (Graph.ErroFacebook e) {
                    sb.append("❌ ").append(p.optString("nome")).append(": ").append(e.getMessage());
                }
            }
            final String m = sb.toString();
            runOnUiThread(() -> txtContaResultado.setText(m));
        }).start();
    }

    // =================================================================== utilidades

    private void abrirSite(String url) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
        } catch (android.content.ActivityNotFoundException e) {
            aviso("Nenhum navegador encontrado.");
        }
    }

    private void aviso(String msg) {
        new AlertDialog.Builder(this).setMessage(msg).setPositiveButton("OK", null).show();
    }
}
