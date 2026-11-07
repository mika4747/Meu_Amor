package com.meuamor.postador;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.time.DayOfWeek;
import java.util.EnumSet;
import java.util.HashSet;
import java.util.Set;

/** Tudo o que o app guarda no celular (só neste app; outros apps não leem). */
public class Dados {

    private final SharedPreferences prefs;

    public Dados(Context ctx) {
        prefs = ctx.getSharedPreferences("postador", Context.MODE_PRIVATE);
    }

    // ------------------------------------------------------------ Página conectada

    public String pageId() { return prefs.getString("page_id", ""); }
    public String pageToken() { return prefs.getString("page_token", ""); }
    public String pageNome() { return prefs.getString("page_nome", ""); }
    public boolean conectado() { return !pageId().isEmpty() && !pageToken().isEmpty(); }

    public void salvarPagina(String id, String nome, String token) {
        prefs.edit().putString("page_id", id).putString("page_nome", nome)
                .putString("page_token", token).apply();
    }

    public void desconectar() {
        prefs.edit().remove("page_id").remove("page_nome").remove("page_token").apply();
    }

    public String appId() { return prefs.getString("app_id", ""); }
    public void salvarAppId(String id) { prefs.edit().putString("app_id", id).apply(); }

    // ------------------------------------------------------------ calendário

    public String horarios() { return prefs.getString("horarios", "09:00, 12:30, 19:00"); }
    public String hashtags() { return prefs.getString("hashtags", ""); }
    public String assinatura() { return prefs.getString("assinatura", ""); }

    public Set<DayOfWeek> dias() {
        String s = prefs.getString("dias", "1234567");
        Set<DayOfWeek> dias = EnumSet.noneOf(DayOfWeek.class);
        for (char c : s.toCharArray()) dias.add(DayOfWeek.of(c - '0'));
        return dias;
    }

    public void salvarCalendario(String horarios, Set<DayOfWeek> dias, String hashtags,
                                 String assinatura) {
        StringBuilder d = new StringBuilder();
        for (DayOfWeek dia : dias) d.append(dia.getValue());
        prefs.edit().putString("horarios", horarios).putString("dias", d.toString())
                .putString("hashtags", hashtags).putString("assinatura", assinatura).apply();
    }

    // ------------------------------------------------------------ histórico

    public JSONArray historico() {
        try {
            return new JSONArray(prefs.getString("historico", "[]"));
        } catch (JSONException e) {
            return new JSONArray();
        }
    }

    /** quando = segundos Unix do agendamento, ou 0 se foi publicado na hora. */
    public void registrar(long quando, String tipo, String resumo, String id) {
        JSONArray h = historico();
        try {
            JSONObject item = new JSONObject();
            item.put("quando", quando);
            item.put("enviado", System.currentTimeMillis() / 1000);
            item.put("tipo", tipo);
            item.put("resumo", resumo);
            item.put("id", id);
            h.put(item);
        } catch (JSONException ignored) {
        }
        // guarda só os 200 mais recentes
        JSONArray recortado = new JSONArray();
        for (int i = Math.max(0, h.length() - 200); i < h.length(); i++) {
            recortado.put(h.opt(i));
        }
        prefs.edit().putString("historico", recortado.toString()).apply();
    }

    public void limparHistorico() { prefs.edit().remove("historico").apply(); }

    /** Horários já usados por posts agendados que ainda não saíram. */
    public Set<Long> ocupados(long agora) {
        Set<Long> s = new HashSet<>();
        JSONArray h = historico();
        for (int i = 0; i < h.length(); i++) {
            long q = h.optJSONObject(i) == null ? 0 : h.optJSONObject(i).optLong("quando");
            if (q > agora) s.add(q);
        }
        return s;
    }
}
