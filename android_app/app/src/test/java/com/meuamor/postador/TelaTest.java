package com.meuamor.postador;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import android.app.AlertDialog;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.net.Uri;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;

import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.Config;
import org.robolectric.annotation.GraphicsMode;
import org.robolectric.shadows.ShadowDialog;
import org.robolectric.shadows.ShadowLooper;

import java.io.File;
import java.io.FileOutputStream;
import java.util.ArrayList;

@RunWith(RobolectricTestRunner.class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(qualifiers = "w393dp-h852dp-xxhdpi")
public class TelaTest {

    private MainActivity abrir() {
        ActivityController<MainActivity> c = Robolectric.buildActivity(MainActivity.class);
        return c.setup().get();
    }

    private void conectarFalso() {
        new Dados(RuntimeEnvironment.getApplication()).salvarPagina("111", "Meu Amor", "TOKEN");
    }

    private String texto(MainActivity a, int id) {
        return ((TextView) a.findViewById(id)).getText().toString();
    }

    /** Salva a tela em app/build/telas/NOME.png (para conferir visualmente). */
    private void foto(MainActivity a, String nome) throws Exception {
        ShadowLooper.idleMainLooper();
        View raiz = a.getWindow().getDecorView();
        int w = raiz.getWidth(), h = raiz.getHeight();
        raiz.measure(View.MeasureSpec.makeMeasureSpec(w, View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec(h, View.MeasureSpec.EXACTLY));
        raiz.layout(0, 0, w, h);
        Bitmap bmp = Bitmap.createBitmap(raiz.getWidth(), raiz.getHeight(), Bitmap.Config.ARGB_8888);
        raiz.draw(new Canvas(bmp));
        File pasta = new File("build/telas");
        pasta.mkdirs();
        try (FileOutputStream out = new FileOutputStream(new File(pasta, nome + ".png"))) {
            bmp.compress(Bitmap.CompressFormat.PNG, 100, out);
        }
    }

    @Test
    public void semPaginaAbreNaAbaConta() throws Exception {
        MainActivity a = abrir();
        assertEquals(View.VISIBLE, a.findViewById(R.id.painelConta).getVisibility());
        assertEquals(View.GONE, a.findViewById(R.id.painelPostar).getVisibility());
        assertEquals("Nenhuma Página conectada", texto(a, R.id.txtPagina));
        foto(a, "3-conta");
    }

    @Test
    public void previaDaLegendaJuntaTudo() throws Exception {
        conectarFalso();
        Dados d = new Dados(RuntimeEnvironment.getApplication());
        d.salvarCalendario("09:00, 19:00", java.util.EnumSet.allOf(java.time.DayOfWeek.class),
                "#meuamor #amor", "💛 Siga a página!");
        MainActivity a = abrir();
        assertEquals(View.VISIBLE, a.findViewById(R.id.painelPostar).getVisibility());
        assertEquals("Página: Meu Amor", texto(a, R.id.txtPagina));

        ((EditText) a.findViewById(R.id.edtLegenda)).setText("Bom dia! ☀️");
        ((EditText) a.findViewById(R.id.edtHashtagsPost)).setText("bomdia, #amor");
        assertEquals("Bom dia! ☀️\n\n💛 Siga a página!\n\n#meuamor #amor #bomdia",
                texto(a, R.id.txtPrevia));
        assertTrue(texto(a, R.id.txtQuando).contains("às 09:00")
                || texto(a, R.id.txtQuando).contains("às 19:00"));
        assertEquals("Agendar", texto(a, R.id.btnEnviar));
        foto(a, "1-postar");

        a.findViewById(R.id.rbAgora).performClick();
        assertEquals("Publicar agora", texto(a, R.id.btnEnviar));
    }

    @Test
    public void salvarHorarios() throws Exception {
        conectarFalso();
        MainActivity a = abrir();
        a.findViewById(R.id.abaAgenda).performClick();
        assertEquals(View.VISIBLE, a.findViewById(R.id.painelAgenda).getVisibility());

        ((EditText) a.findViewById(R.id.edtHorarios)).setText("25:00");
        a.findViewById(R.id.btnSalvarAgenda).performClick();
        AlertDialog erro = (AlertDialog) ShadowDialog.getLatestDialog();
        assertTrue(erro.isShowing());
        erro.dismiss();

        ((EditText) a.findViewById(R.id.edtHorarios)).setText("19h 8:00");
        ((EditText) a.findViewById(R.id.edtHashtagsPadrao)).setText("amor viagem");
        a.findViewById(R.id.btnSalvarAgenda).performClick();
        assertEquals("08:00, 19:00", texto(a, R.id.edtHorarios));
        assertEquals("#amor #viagem", texto(a, R.id.edtHashtagsPadrao));
        assertTrue(texto(a, R.id.txtProximos).startsWith("Próximos horários livres:\n• "));
        foto(a, "2-horarios");
    }

    @Test
    public void enviarSemPaginaPedeConexao() {
        MainActivity a = abrir();
        a.findViewById(R.id.abaPostar).performClick();
        ((EditText) a.findViewById(R.id.edtLegenda)).setText("Oi");
        a.findViewById(R.id.btnEnviar).performClick();
        assertEquals(View.VISIBLE, a.findViewById(R.id.painelConta).getVisibility());
        assertTrue(ShadowDialog.getLatestDialog().isShowing());
    }

    @Test
    public void enviarPedeConfirmacaoComResumo() {
        conectarFalso();
        MainActivity a = abrir();
        ((EditText) a.findViewById(R.id.edtLegenda)).setText("Teste");
        a.findViewById(R.id.btnEnviar).performClick();
        AlertDialog d = (AlertDialog) ShadowDialog.getLatestDialog();
        assertTrue(d.isShowing());
        assertEquals("Agendar", d.getButton(AlertDialog.BUTTON_POSITIVE).getText().toString());
    }

    @Test
    public void receberFotosCompartilhadasDaGaleria() {
        conectarFalso();
        Intent i = new Intent(Intent.ACTION_SEND_MULTIPLE);
        i.setType("image/*");
        ArrayList<Uri> uris = new ArrayList<>();
        uris.add(Uri.parse("content://galeria/1"));
        uris.add(Uri.parse("content://galeria/2"));
        i.putParcelableArrayListExtra(Intent.EXTRA_STREAM, uris);
        MainActivity a = Robolectric.buildActivity(MainActivity.class, i).setup().get();
        ShadowLooper.idleMainLooper();
        assertEquals("📷 2 fotos escolhidas (saem juntas num só post)", texto(a, R.id.txtMidia));
    }

    @Test
    public void cancelarDesconexaoMantemPagina() {
        conectarFalso();
        MainActivity a = abrir();
        a.findViewById(R.id.abaConta).performClick();
        assertTrue(texto(a, R.id.txtContaStatus).contains("Meu Amor"));
        ((Button) a.findViewById(R.id.btnDesconectar)).performClick();
        AlertDialog d = (AlertDialog) ShadowDialog.getLatestDialog();
        d.getButton(AlertDialog.BUTTON_POSITIVE).performClick();
        ShadowLooper.idleMainLooper();
        assertEquals("Nenhuma Página conectada", texto(a, R.id.txtPagina));
    }
}
