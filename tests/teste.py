#!/usr/bin/env python3
"""Testes do gerador, rodando sobre respostas reais da API guardadas em fixtures.

    python tests/teste.py

Sem dependencias: so assert e biblioteca padrao.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

import gerar_ics as g  # noqa: E402

FIXTURES = RAIZ / "tests" / "fixtures"
falhas: list[str] = []


def checar(descricao: str, obtido: object, esperado: object) -> None:
    if obtido == esperado:
        print(f"  ok  {descricao}")
    else:
        print(f"  XX  {descricao}\n        obtido:   {obtido!r}\n        esperado: {esperado!r}")
        falhas.append(descricao)


def carregar(nome: str) -> list[dict]:
    dados = json.loads((FIXTURES / nome).read_text(encoding="utf-8"))
    eventos = []
    if "meses" in dados:
        for bloco in dados["meses"]:
            for jogo in bloco.get("jogos") or []:
                if g.util(jogo):
                    eventos.append(g.montar_evento(jogo, int(bloco["ano"])))
    else:
        for jogo in dados["jogos"]:
            if g.util(jogo):
                eventos.append(g.montar_evento(jogo, 2026))
    return eventos


def por_uid(eventos: list[dict], ident: str) -> dict:
    return next(e for e in eventos if e["uid"].startswith(f"jogo-{ident}@"))


def inicio_utc(evento: dict) -> str:
    return g.utc(evento["inicio"])


print("outubro de 2026 (jogos no Brasil)")
out = carregar("jogos-2026-10.json")
checar("descarta os registros-fantasma da API", len(out), 8)
# 14/10 21h30 em Brasilia = 15/10 00h30 UTC — o caso que o FootCal errou
checar("semifinal da Libertadores (ida)", inicio_utc(por_uid(out, "5250")), "20261015T003000Z")
checar("semifinal da Libertadores (volta)", inicio_utc(por_uid(out, "5249")), "20261022T003000Z")
checar("Brasileirão 21h30", inicio_utc(por_uid(out, "4691")), "20261009T003000Z")
checar("resumo com placar quando o jogo acabou",
       por_uid(out, "4600")["resumo"], "⚽ Palmeiras 2 x 1 Grêmio [Brasileirão]")
checar("UID vem do id da API", por_uid(out, "4691")["uid"],
       f"jogo-4691@{g.DOMINIO_UID}")

print("\ncasos limite")
lim = carregar("casos-limite.json")
# A API grava o horario local do estadio; fora do Brasil precisa converter.
checar("fora do país, com hora_alt de conferência (Barranquilla, UTC-5)",
       inicio_utc(por_uid(lim, "4902")), "20260409T003000Z")
checar("fora do país, com hora_alt de conferência (Lima, UTC-5)",
       inicio_utc(por_uid(lim, "4831")), "20260505T220000Z")
checar("fora do país, sem hora_alt (Quito, UTC-5)",
       inicio_utc(por_uid(lim, "5147")), "20260916T220000Z")
checar("em casa contra adversário estrangeiro usa Brasília",
       inicio_utc(por_uid(lim, "5148")), "20260909T220000Z")
checar("00H00 significa 'a definir', não meia-noite",
       por_uid(lim, "4697")["inicio"], None)
checar("sem horário vira evento de dia inteiro",
       por_uid(lim, "4697")["data"], dt.date(2026, 11, 18))
checar("estádio nulo não gera LOCATION", por_uid(lim, "4699")["local"], "")
checar("HTML da transmissão é removido", por_uid(lim, "4902")["tv"],
       "Globo/getv e ESPN/Disney+")

print("\nnomes de competição")
for bruto, curto in [
    ("Brasileirão Série A 2026", "Brasileirão"),
    ("Brasileiro", "Brasileirão"),
    ("Libertadores 2026", "Libertadores"),
    ("Paulista", "Paulistão"),
    ("Copa do Brasil", "Copa do Brasil"),
    ("Copa Paulista", "Copa Paulista"),
]:
    checar(f"{bruto!r} -> {curto!r}", g.competicao_curta(bruto), curto)

print("\nformato do arquivo")
agora = dt.datetime(2026, 10, 7, 12, 0, tzinfo=dt.timezone.utc)
ics = g.montar_ics(out, agora)
checar("termina em END:VCALENDAR", ics.strip().endswith("END:VCALENDAR"), True)
checar("usa CRLF", "\r\n" in ics, True)
checar("um VEVENT por jogo", ics.count("BEGIN:VEVENT"), len(out))
checar("declara intervalo de atualização",
       "REFRESH-INTERVAL;VALUE=DURATION:PT6H" in ics, True)
checar("nenhuma linha passa de 75 octetos",
       max(len(l.encode("utf-8")) for l in ics.split("\r\n")), 75)
checar("eventos em ordem cronológica",
       [e["data"] for e in sorted(out, key=lambda e: e["data"])],
       sorted(e["data"] for e in out))

print("\ntravas de segurança")
hoje = dt.date(2026, 10, 7)
for descricao, eventos, anterior in [
    ("poucos jogos aborta", out[:2], None),
    ("queda brusca no total aborta", out[:5], "BEGIN:VEVENT" * 40),
    ("sem jogo futuro aborta", [dict(e, data=dt.date(2020, 1, 1)) for e in out], None),
]:
    try:
        g.conferir(eventos, hoje, anterior)
        checar(descricao, "nao abortou", "SystemExit")
    except SystemExit:
        print(f"  ok  {descricao}")

try:
    g.conferir(out, hoje, None)
    print("  ok  dados bons passam")
except SystemExit as erro:
    checar("dados bons passam", str(erro), "sem erro")

print("\nerros de rede")
import http.client  # noqa: E402
import socket  # noqa: E402
import urllib.error  # noqa: E402
from email.message import Message  # noqa: E402

cabecalho = Message()
cabecalho["Server"] = "nginx"
for descricao, erro, esperado in [
    ("HTTP 499 e bloqueio", urllib.error.HTTPError("u", 499, "", cabecalho, None), "bloqueio"),
    ("HTTP 403 e bloqueio", urllib.error.HTTPError("u", 403, "", cabecalho, None), "bloqueio"),
    ("HTTP 500 nao e bloqueio", urllib.error.HTTPError("u", 500, "", cabecalho, None), "http"),
    ("conexao fechada sem resposta e bloqueio", http.client.RemoteDisconnected("x"), "bloqueio"),
    ("reset embrulhado em URLError e bloqueio", urllib.error.URLError(ConnectionResetError()), "bloqueio"),
    ("DNS falhando e rede", urllib.error.URLError(socket.gaierror(-2, "Name not known")), "rede"),
    ("JSON quebrado e formato", ValueError("Expecting value"), "formato"),
]:
    checar(descricao, g.classificar_erro(erro)[0], esperado)

buscar_original = g.buscar_mes


def bloqueado(ano, mes):
    raise http.client.RemoteDisconnected("Remote end closed connection without response")


g.buscar_mes = bloqueado
try:
    g.coletar(hoje)
    checar("todos os meses bloqueados aborta", "nao abortou", "SystemExit")
except SystemExit:
    print("  ok  todos os meses bloqueados aborta")

mes_bom = g.meses_da_janela(hoje)[0]
g.buscar_mes = lambda ano, mes: [{"id": "1", "time_casa": "Palmeiras", "time_visitante": "X",
                                  "data_jogo": "10/10"}] if (ano, mes) == mes_bom else bloqueado(ano, mes)
checar("falha parcial segue com o que conseguiu", len(g.coletar(hoje)), 1)
g.buscar_mes = buscar_original

total = len(g.meses_da_janela(hoje))
diag = g.diagnosticar([(f"{i:02d}/2026", "bloqueio", "HTTP 499 (Server: nginx)") for i in range(total)], total)
checar("diagnostico aponta bloqueio quando tudo foi recusado", "bloqueio por IP/WAF" in diag, True)

print()
if falhas:
    print(f"{len(falhas)} falha(s): " + "; ".join(falhas))
    sys.exit(1)
print("todos os testes passaram")
