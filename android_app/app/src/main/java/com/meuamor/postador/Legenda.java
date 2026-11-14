package com.meuamor.postador;

import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZonedDateTime;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.TreeSet;

/** Legendas, hashtags e cálculo dos horários do calendário (sem dependência do Android). */
public final class Legenda {

    /** O Facebook só aceita agendar entre 10 minutos e 30 dias à frente. */
    public static final long MINIMO_S = 10 * 60;
    public static final long MAXIMO_S = 30L * 24 * 60 * 60;

    private Legenda() {}

    /** "amor, #Foto viagem" -> [#amor, #Foto, #viagem], sem repetir (ignora maiúsculas). */
    public static List<String> hashtags(String... grupos) {
        List<String> saida = new ArrayList<>();
        Set<String> vistas = new HashSet<>();
        for (String grupo : grupos) {
            if (grupo == null) continue;
            for (String item : grupo.replace(",", " ").trim().split("\\s+")) {
                String tag = item.replaceAll("^#+", "");
                if (tag.isEmpty()) continue;
                tag = "#" + tag;
                if (vistas.add(tag.toLowerCase(Locale.ROOT))) saida.add(tag);
            }
        }
        return saida;
    }

    /** Texto + assinatura + hashtags (sem repetir hashtags que já estão no texto). */
    public static String montar(String mensagem, String assinatura, List<String> hashtags) {
        StringBuilder sb = new StringBuilder();
        for (String parte : new String[]{mensagem, assinatura}) {
            if (parte != null && !parte.trim().isEmpty()) {
                if (sb.length() > 0) sb.append("\n\n");
                sb.append(parte.trim());
            }
        }
        Set<String> noTexto = new HashSet<>();
        for (String palavra : sb.toString().split("\\s+")) {
            noTexto.add(palavra.toLowerCase(Locale.ROOT).replaceAll("[.,!?;:]+$", ""));
        }
        StringBuilder tags = new StringBuilder();
        for (String h : hashtags) {
            if (!noTexto.contains(h.toLowerCase(Locale.ROOT))) {
                if (tags.length() > 0) tags.append(' ');
                tags.append(h);
            }
        }
        if (tags.length() > 0) {
            if (sb.length() > 0) sb.append("\n\n");
            sb.append(tags);
        }
        return sb.toString();
    }

    /** "09:00, 12:30 19h" -> [09:00, 12:30, 19:00]. */
    public static List<LocalTime> horarios(String texto) {
        TreeSet<LocalTime> hs = new TreeSet<>();
        for (String item : texto.replace(";", ",").replace(" ", ",").split(",")) {
            String s = item.trim().toLowerCase(Locale.ROOT).replace("h", ":");
            if (s.isEmpty()) continue;
            if (s.endsWith(":")) s += "00";
            String[] partes = s.split(":");
            try {
                int h = Integer.parseInt(partes[0]);
                int m = partes.length > 1 && !partes[1].isEmpty() ? Integer.parseInt(partes[1]) : 0;
                hs.add(LocalTime.of(h, m));
            } catch (RuntimeException e) {
                throw new IllegalArgumentException("Horário inválido: \"" + item.trim()
                        + "\". Use o formato 09:00.");
            }
        }
        return new ArrayList<>(hs);
    }

    /** Próximo horário do calendário que esteja livre e que o Facebook aceite. */
    public static ZonedDateTime proximoLivre(List<LocalTime> horarios, Set<DayOfWeek> dias,
                                             Set<Long> ocupados, ZonedDateTime agora) {
        ZonedDateTime inicio = agora.plusSeconds(MINIMO_S + 5 * 60); // 5 min de folga
        ZonedDateTime fim = agora.plusSeconds(MAXIMO_S - 60 * 60);
        for (LocalDate dia = inicio.toLocalDate(); !dia.isAfter(fim.toLocalDate());
             dia = dia.plusDays(1)) {
            if (!dias.contains(dia.getDayOfWeek())) continue;
            for (LocalTime h : horarios) {
                ZonedDateTime dt = dia.atTime(h).atZone(agora.getZone());
                if (!dt.isBefore(inicio) && !dt.isAfter(fim)
                        && !ocupados.contains(dt.toEpochSecond())) {
                    return dt;
                }
            }
        }
        return null;
    }

    /** null se o horário for aceito; senão, a mensagem de erro. */
    public static String problemaNoHorario(long quando, long agora) {
        long dif = quando - agora;
        if (dif < MINIMO_S) return "O horário precisa ser pelo menos 10 minutos no futuro.";
        if (dif > MAXIMO_S) return "O Facebook só agenda até 30 dias à frente.";
        return null;
    }
}
