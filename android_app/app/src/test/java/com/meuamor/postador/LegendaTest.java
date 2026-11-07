package com.meuamor.postador;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertThrows;

import org.junit.Test;

import java.time.DayOfWeek;
import java.time.LocalTime;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.Arrays;
import java.util.Collections;
import java.util.EnumSet;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class LegendaTest {

    private static final ZoneOffset BRT = ZoneOffset.ofHours(-3);
    // sábado, 07/11/2026, 10:00
    private static final ZonedDateTime AGORA = ZonedDateTime.of(2026, 11, 7, 10, 0, 0, 0, BRT);

    @Test
    public void hashtagsNormalizadasSemRepetir() {
        assertEquals(Arrays.asList("#amor", "#Viagem", "#foto", "#praia"),
                Legenda.hashtags("amor #Viagem", "viagem, #foto  praia", null));
        assertEquals(Collections.emptyList(), Legenda.hashtags("", "  "));
    }

    @Test
    public void montarLegenda() {
        assertEquals("Oi\n\nSiga!\n\n#a #b",
                Legenda.montar("Oi", "Siga!", Arrays.asList("#a", "#b")));
        assertEquals("Muito #amor!\n\n#x",
                Legenda.montar("Muito #amor!", "", Arrays.asList("#amor", "#x")));
        assertEquals("#a", Legenda.montar("", null, Collections.singletonList("#a")));
        assertEquals("", Legenda.montar("  ", "", Collections.emptyList()));
    }

    @Test
    public void lerHorarios() {
        assertEquals(Arrays.asList(LocalTime.of(9, 0), LocalTime.of(12, 30), LocalTime.of(19, 0)),
                Legenda.horarios("19h, 09:00 12:30, 9:00"));
        assertEquals(Collections.singletonList(LocalTime.of(9, 30)), Legenda.horarios("9h30"));
        assertThrows(IllegalArgumentException.class, () -> Legenda.horarios("25:00"));
        assertThrows(IllegalArgumentException.class, () -> Legenda.horarios("amanhã"));
    }

    @Test
    public void proximoHorarioLivre() {
        List<LocalTime> hs = Arrays.asList(LocalTime.of(9, 0), LocalTime.of(19, 0));
        Set<DayOfWeek> todos = EnumSet.allOf(DayOfWeek.class);
        assertEquals(ZonedDateTime.of(2026, 11, 7, 19, 0, 0, 0, BRT),
                Legenda.proximoLivre(hs, todos, new HashSet<>(), AGORA));

        Set<Long> ocupados = new HashSet<>();
        ocupados.add(ZonedDateTime.of(2026, 11, 7, 19, 0, 0, 0, BRT).toEpochSecond());
        assertEquals(ZonedDateTime.of(2026, 11, 8, 9, 0, 0, 0, BRT),
                Legenda.proximoLivre(hs, todos, ocupados, AGORA));
    }

    @Test
    public void respeitaDiasEMinimoDe10Minutos() {
        // 10:10 está a menos de 15 min (10 do Facebook + 5 de folga): pula
        List<LocalTime> hs = Arrays.asList(LocalTime.of(10, 10), LocalTime.of(11, 0));
        assertEquals(ZonedDateTime.of(2026, 11, 7, 11, 0, 0, 0, BRT),
                Legenda.proximoLivre(hs, EnumSet.allOf(DayOfWeek.class), new HashSet<>(), AGORA));

        // só segundas: próxima é 09/11
        assertEquals(ZonedDateTime.of(2026, 11, 9, 9, 0, 0, 0, BRT),
                Legenda.proximoLivre(Collections.singletonList(LocalTime.of(9, 0)),
                        EnumSet.of(DayOfWeek.MONDAY), new HashSet<>(), AGORA));
    }

    @Test
    public void semVagaEm30Dias() {
        Set<Long> ocupados = new HashSet<>();
        ZonedDateTime dia = AGORA;
        for (int i = 0; i < 32; i++) {
            ocupados.add(dia.plusDays(i).withHour(19).withMinute(0).toEpochSecond());
        }
        assertNull(Legenda.proximoLivre(Collections.singletonList(LocalTime.of(19, 0)),
                EnumSet.allOf(DayOfWeek.class), ocupados, AGORA));
    }

    @Test
    public void limitesDoFacebook() {
        long agora = 1_000_000;
        assertNotNull(Legenda.problemaNoHorario(agora + 5 * 60, agora));
        assertNotNull(Legenda.problemaNoHorario(agora + 31L * 86400, agora));
        assertNull(Legenda.problemaNoHorario(agora + 86400, agora));
    }
}
