#!/usr/bin/env python3
"""Gera um calendario iCalendar (.ics) com todos os jogos do Palmeiras.

Fonte: API publica do proprio site do clube.
    https://www.palmeiras.com.br/wp-json/apiverdao/v1/jogos-mes?mes=MM&ano=AAAA

A API devolve um mes por chamada, entao o script varre uma janela de meses e
junta tudo. Cada jogo tem um "id" estavel, usado como UID do evento: quando a
CBF ou a Conmebol muda o horario, o evento e EDITADO no seu calendario em vez
de aparecer duplicado.

Uso:
    python scripts/gerar_ics.py                  # busca na API e grava em docs/
    python scripts/gerar_ics.py --entrada tests/fixtures/jogos-2026-10.json \
        --ano 2026 --saida /tmp/teste.ics        # modo offline, para testes

Sem dependencias externas: so biblioteca padrao (urllib + zoneinfo).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

API = "https://www.palmeiras.com.br/wp-json/apiverdao/v1/jogos-mes"
TZ = ZoneInfo("America/Sao_Paulo")
UA = "calendario-palmeiras/1.0 (+https://github.com/GusLFSantos/calendario-palmeiras)"

DURACAO = dt.timedelta(hours=2)
DOMINIO_UID = "calendario-palmeiras.github.io"

# Rede de seguranca: se a API mudar de formato, e melhor falhar alto do que
# publicar um calendario vazio que o Google vai sincronizar em cima do bom.
MIN_EVENTOS = 5
QUEDA_MAXIMA = 0.5  # falha se o total cair para menos da metade do anterior

RE_DATA = re.compile(r"^(\d{2})/(\d{2})$")
RE_HORA = re.compile(r"^(\d{1,2})[:Hh](\d{2})$")
RE_TAG = re.compile(r"<[^>]+>")
RE_SUFIXO_PAIS = re.compile(r"-([A-Z]{3})\s*$")

# A API grava o horario LOCAL DO ESTADIO. Quando o Palmeiras joga fora do
# Brasil, o adversario vem com sufixo de pais ("Cerro Porteno-PAR") e o
# horario precisa ser interpretado no fuso de la. Conferido contra tres jogos
# de 2026 (Junior-COL, Sporting Cristal-PER, LDU-EQU).
FUSO_POR_PAIS = {
    "ARG": "America/Argentina/Buenos_Aires",
    "BOL": "America/La_Paz",
    "BRA": "America/Sao_Paulo",
    "CHI": "America/Santiago",
    "COL": "America/Bogota",
    "ECU": "America/Guayaquil",
    "EQU": "America/Guayaquil",
    "MEX": "America/Mexico_City",
    "PAR": "America/Asuncion",
    "PER": "America/Lima",
    "URU": "America/Montevideo",
    "USA": "America/New_York",
    "VEN": "America/Caracas",
}


# --------------------------------------------------------------------------- #
# Busca
# --------------------------------------------------------------------------- #

def meses_da_janela(hoje: dt.date, antes: int = 2, depois: int = 14) -> list[tuple[int, int]]:
    """Meses a consultar: alguns para tras (resultados) e um ano e pouco adiante."""
    meses: list[tuple[int, int]] = []
    ano, mes = hoje.year, hoje.month
    # recua
    for _ in range(antes):
        mes -= 1
        if mes == 0:
            ano, mes = ano - 1, 12
    for _ in range(antes + depois + 1):
        meses.append((ano, mes))
        mes += 1
        if mes == 13:
            ano, mes = ano + 1, 1
    return meses


def buscar_mes(ano: int, mes: int, timeout: int = 30) -> list[dict]:
    url = f"{API}?mes={mes:02d}&ano={ano}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        dados = json.loads(resp.read().decode("utf-8"))
    jogos = dados.get("jogos") or []
    if not isinstance(jogos, list):
        raise ValueError(f"{url}: campo 'jogos' nao e uma lista")
    return jogos


def coletar(hoje: dt.date) -> list[tuple[dict, int]]:
    """Devolve pares (jogo, ano_consultado), sem duplicatas, na ordem da data."""
    vistos: set[str] = set()
    coletados: list[tuple[dict, int]] = []
    falhas: list[str] = []

    for ano, mes in meses_da_janela(hoje):
        try:
            jogos = buscar_mes(ano, mes)
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError) as erro:
            falhas.append(f"{mes:02d}/{ano}: {erro}")
            continue
        for jogo in jogos:
            if not util(jogo):
                continue  # meses sem tabela publicada devolvem um registro vazio
            ident = str(jogo["id"])
            if ident in vistos:
                continue
            vistos.add(ident)
            coletados.append((jogo, ano))

    if falhas:
        print("avisos na busca:", "; ".join(falhas), file=sys.stderr)
    # se TODOS os meses falharam, nao ha o que publicar
    if not coletados and falhas:
        raise SystemExit("erro: nenhum mes pudo ser lido da API — abortando sem gravar")
    return coletados


def util(jogo: object) -> bool:
    """Filtra os registros-fantasma que a API devolve para meses sem tabela."""
    if not isinstance(jogo, dict):
        return False
    if not jogo.get("id"):
        return False
    if not RE_DATA.match(str(jogo.get("data_jogo") or "")):
        return False
    return bool(jogo.get("time_casa")) and bool(jogo.get("time_visitante"))


# --------------------------------------------------------------------------- #
# Transformacao
# --------------------------------------------------------------------------- #

def competicao_curta(nome: str) -> str:
    n = (nome or "").strip()
    baixo = n.lower()
    if "brasileir" in baixo:
        return "Brasileirão"
    if "libertadores" in baixo:
        return "Libertadores"
    if "sul-americana" in baixo or "sudamericana" in baixo:
        return "Sul-Americana"
    if "copa do brasil" in baixo:
        return "Copa do Brasil"
    if "paulista" in baixo and "copa" not in baixo:
        return "Paulistão"
    if "mundial" in baixo or "intercontinental" in baixo:
        return "Mundial"
    if "supercopa" in baixo:
        return "Supercopa"
    # remove o ano do fim ("Alguma Coisa 2026" -> "Alguma Coisa")
    return re.sub(r"\s*(19|20)\d{2}\s*$", "", n) or "Jogo"


def ano_do_jogo(dia: int, mes: int, ano_consulta: int, mes_consulta: int | None) -> int:
    """A API nao manda o ano; vem da consulta. Trata a virada dez/jan."""
    if mes_consulta is None:
        return ano_consulta
    if mes_consulta == 12 and mes == 1:
        return ano_consulta + 1
    if mes_consulta == 1 and mes == 12:
        return ano_consulta - 1
    return ano_consulta


def limpar(texto: object) -> str:
    """Remove as tags HTML que a API embute em alguns campos."""
    return RE_TAG.sub("", str(texto or "")).replace("&amp;", "&").strip()


def fuso_do_estadio(casa: str, fora: str) -> ZoneInfo:
    if "palmeiras" in fora.lower():  # Palmeiras visitante -> estadio do adversario
        casada = RE_SUFIXO_PAIS.search(casa.strip())
        if casada:
            nome = FUSO_POR_PAIS.get(casada.group(1))
            if nome:
                return ZoneInfo(nome)
    return TZ


def ler_hora(bruta: object) -> tuple[int, int] | None:
    """00H00 na API significa 'a definir', nao meia-noite."""
    casada = RE_HORA.match(str(bruta or "").strip())
    if not casada:
        return None
    hora, minuto = int(casada.group(1)), int(casada.group(2))
    if (hora, minuto) == (0, 0):
        return None
    if not (0 <= hora <= 23 and 0 <= minuto <= 59):
        return None
    return hora, minuto


def montar_evento(jogo: dict, ano_consulta: int) -> dict:
    dia_s, mes_s = RE_DATA.match(str(jogo["data_jogo"])).groups()
    dia, mes = int(dia_s), int(mes_s)
    ano = ano_do_jogo(dia, mes, ano_consulta, mes)
    data = dt.date(ano, mes, dia)

    casa = limpar(jogo["time_casa"])
    fora = limpar(jogo["time_visitante"])

    relogio = ler_hora(jogo.get("hora1")) or ler_hora(jogo.get("hora"))
    if relogio:
        fuso = fuso_do_estadio(casa, fora)
        inicio = dt.datetime(ano, mes, dia, relogio[0], relogio[1], tzinfo=fuso)
        # hora_alt, quando existe, e o mesmo jogo em horario de Brasilia:
        # serve de conferencia da conversao de fuso.
        conferencia = ler_hora(jogo.get("hora_alt"))
        if conferencia and fuso is not TZ:
            esperado = dt.datetime(ano, mes, dia, conferencia[0], conferencia[1], tzinfo=TZ)
            if abs((esperado - inicio).total_seconds()) > 60:
                print(
                    f"aviso: {casa} x {fora} em {data:%d/%m/%Y}: horario local "
                    f"{relogio[0]:02d}:{relogio[1]:02d} ({fuso}) nao casa com "
                    f"hora_alt {conferencia[0]:02d}:{conferencia[1]:02d} de Brasilia",
                    file=sys.stderr,
                )
    else:
        inicio = None  # horario ainda nao definido -> evento de dia inteiro
    gols_casa = limpar(jogo.get("placar_casa"))
    gols_fora = limpar(jogo.get("placar_visitante"))
    competicao = competicao_curta(limpar(jogo.get("campeonato")))

    if gols_casa != "" and gols_fora != "":
        confronto = f"{casa} {gols_casa} x {gols_fora} {fora}"
    else:
        confronto = f"{casa} x {fora}"

    rodada = limpar(jogo.get("rodada"))
    estadio = limpar(jogo.get("estadio"))
    tv = limpar(jogo.get("excecao"))

    linhas = [f"Competição: {limpar(jogo.get('campeonato')) or competicao}"]
    if rodada:
        linhas.append(f"Fase: {rodada}")
    if estadio:
        linhas.append(f"Estádio: {estadio}")
    if tv:
        linhas.append(f"Transmissão: {tv}")
    if inicio is None:
        linhas.append("Horário ainda não confirmado pela entidade organizadora.")
    linhas.append("Fonte: https://www.palmeiras.com.br/calendario/")

    return {
        "uid": f"jogo-{jogo['id']}@{DOMINIO_UID}",
        "data": data,
        "inicio": inicio,
        "resumo": f"[{competicao}] {confronto}",
        "local": estadio,
        "descricao": "\n".join(linhas),
        "rodada": rodada,
        "competicao": competicao,
        "confronto": confronto,
        "tv": tv,
    }


# --------------------------------------------------------------------------- #
# iCalendar
# --------------------------------------------------------------------------- #

def escapar(texto: str) -> str:
    return (
        texto.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def dobrar(linha: str) -> str:
    """Dobra linhas longas em 75 octetos, como pede o RFC 5545."""
    bruto = linha.encode("utf-8")
    if len(bruto) <= 75:
        return linha
    partes, atual = [], b""
    for caractere in linha:
        octetos = caractere.encode("utf-8")
        limite = 75 if not partes else 74  # continuacao gasta 1 octeto com o espaco
        if len(atual) + len(octetos) > limite:
            partes.append(atual)
            atual = b""
        atual += octetos
    partes.append(atual)
    return "\r\n ".join(p.decode("utf-8") for p in partes)


def utc(momento: dt.datetime) -> str:
    return momento.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def bloco_evento(evento: dict, agora: dt.datetime) -> list[str]:
    linhas = ["BEGIN:VEVENT", f"UID:{evento['uid']}", f"DTSTAMP:{utc(agora)}", "SEQUENCE:0"]
    if evento["inicio"] is None:
        fim = evento["data"] + dt.timedelta(days=1)
        linhas.append(f"DTSTART;VALUE=DATE:{evento['data'].strftime('%Y%m%d')}")
        linhas.append(f"DTEND;VALUE=DATE:{fim.strftime('%Y%m%d')}")
    else:
        linhas.append(f"DTSTART:{utc(evento['inicio'])}")
        linhas.append(f"DTEND:{utc(evento['inicio'] + DURACAO)}")
    linhas.append(f"SUMMARY:{escapar(evento['resumo'])}")
    if evento["local"]:
        linhas.append(f"LOCATION:{escapar(evento['local'])}")
    linhas.append(f"DESCRIPTION:{escapar(evento['descricao'])}")
    linhas.append("END:VEVENT")
    return linhas


def montar_ics(eventos: list[dict], agora: dt.datetime) -> str:
    linhas = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//calendario-palmeiras//Jogos do Palmeiras//PT-BR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "NAME:Palmeiras",
        "X-WR-CALNAME:Palmeiras",
        "X-WR-TIMEZONE:America/Sao_Paulo",
        "X-WR-CALDESC:Jogos do Palmeiras em todas as competições\\, direto do site oficial do clube.",
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
        "X-PUBLISHED-TTL:PT6H",
    ]
    for evento in sorted(eventos, key=lambda e: (e["data"], e["inicio"] or dt.datetime.min.replace(tzinfo=TZ))):
        linhas.extend(bloco_evento(evento, agora))
    linhas.append("END:VCALENDAR")
    return "\r\n".join(dobrar(l) for l in linhas) + "\r\n"


# --------------------------------------------------------------------------- #
# Verificacoes de sanidade — o que impede o calendario de apodrecer em silencio
# --------------------------------------------------------------------------- #

def conferir(eventos: list[dict], hoje: dt.date, ics_anterior: str | None) -> None:
    if len(eventos) < MIN_EVENTOS:
        raise SystemExit(
            f"erro: so {len(eventos)} jogo(s) extraido(s), minimo esperado {MIN_EVENTOS}. "
            "A API provavelmente mudou de formato. Nada foi gravado."
        )

    futuros = [e for e in eventos if e["data"] >= hoje]
    if not futuros:
        raise SystemExit("erro: nenhum jogo futuro na lista. Nada foi gravado.")

    limite_passado = hoje - dt.timedelta(days=400)
    limite_futuro = hoje + dt.timedelta(days=900)
    fora = [e for e in eventos if not (limite_passado <= e["data"] <= limite_futuro)]
    if fora:
        amostra = ", ".join(f"{e['data']:%d/%m/%Y} {e['confronto']}" for e in fora[:3])
        raise SystemExit(f"erro: datas implausiveis ({amostra}). Nada foi gravado.")

    if ics_anterior:
        antes = ics_anterior.count("BEGIN:VEVENT")
        if antes and len(eventos) < antes * QUEDA_MAXIMA:
            raise SystemExit(
                f"erro: o total caiu de {antes} para {len(eventos)} jogos. "
                "Suspeita de resposta parcial da API. Nada foi gravado."
            )

    print(f"ok: {len(eventos)} jogos ({len(futuros)} futuros)")
    por_competicao: dict[str, int] = {}
    for evento in eventos:
        por_competicao[evento["competicao"]] = por_competicao.get(evento["competicao"], 0) + 1
    for nome, quantos in sorted(por_competicao.items(), key=lambda p: -p[1]):
        print(f"     {nome}: {quantos}")


# --------------------------------------------------------------------------- #
# Gravacao
# --------------------------------------------------------------------------- #

VOLATEIS = ("DTSTAMP:", "X-GERADO-EM:")


def normalizar(conteudo: str) -> str:
    """Conteudo sem as linhas que mudam a cada execucao, para comparar de verdade."""
    return "\n".join(
        l for l in conteudo.splitlines() if not l.startswith(VOLATEIS)
    )


def gravar_se_mudou(caminho: Path, novo: str) -> bool:
    antigo = caminho.read_text(encoding="utf-8") if caminho.exists() else None
    if antigo is not None and normalizar(antigo) == normalizar(novo):
        print(f"sem mudancas em {caminho}")
        return False
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(novo, encoding="utf-8", newline="")
    print(f"gravado {caminho}")
    return True


def montar_index(eventos: list[dict], hoje: dt.date, url_ics: str) -> str:
    futuros = sorted(
        (e for e in eventos if e["data"] >= hoje),
        key=lambda e: (e["data"], e["inicio"] or dt.datetime.min.replace(tzinfo=TZ)),
    )[:12]
    linhas = []
    for e in futuros:
        quando = f"{e['data']:%d/%m}"
        quando += f" · {e['inicio']:%H:%M}" if e["inicio"] else " · horário a confirmar"
        extra = " · ".join(x for x in (e["local"], e["tv"]) if x)
        linhas.append(
            f"      <tr><td>{quando}</td><td>{e['competicao']}</td>"
            f"<td>{e['confronto']}</td><td>{extra}</td></tr>"
        )
    tabela = "\n".join(linhas) or '      <tr><td colspan="4">Sem jogos futuros publicados.</td></tr>'
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Calendário do Palmeiras</title>
<style>
  :root {{ color-scheme: light dark; --fundo:#ffffff; --texto:#14281d; --linha:#dfe6e1; --verde:#036d41; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --fundo:#101512; --texto:#e8f0ea; --linha:#26302a; --verde:#4ec98c; }}
  }}
  body {{ margin:0; padding:40px 16px; background:var(--fundo); color:var(--texto);
         font:16px/1.55 ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }}
  main {{ max-width:760px; margin:0 auto; }}
  h1 {{ font-size:1.5rem; margin:0 0 4px; }}
  p.sub {{ margin:0 0 28px; opacity:.72; }}
  code {{ background:color-mix(in srgb, var(--texto) 8%, transparent); padding:3px 7px;
          border-radius:5px; font-size:.86em; word-break:break-all; }}
  table {{ width:100%; border-collapse:collapse; margin-top:12px; font-size:.93rem; }}
  th, td {{ text-align:left; padding:9px 10px; border-bottom:1px solid var(--linha); vertical-align:top; }}
  th {{ font-size:.74rem; text-transform:uppercase; letter-spacing:.07em; opacity:.6; font-weight:600; }}
  td:nth-child(2) {{ color:var(--verde); white-space:nowrap; }}
  td:nth-child(4) {{ opacity:.66; font-size:.88em; }}
  footer {{ margin-top:32px; font-size:.84rem; opacity:.6; }}
  a {{ color:var(--verde); }}
</style>
</head>
<body>
<main>
  <h1>Calendário do Palmeiras</h1>
  <p class="sub">Todas as competições, horário de Brasília, direto do site oficial do clube.</p>

  <p>Assine esta URL no Google Agenda (Outras agendas → + → Do URL):</p>
  <p><code>{url_ics}</code></p>

  <table>
    <thead><tr><th>Data</th><th>Competição</th><th>Jogo</th><th>Local e TV</th></tr></thead>
    <tbody>
{tabela}
    </tbody>
  </table>

  <footer>
    Atualizado em {hoje:%d/%m/%Y} · fonte:
    <a href="https://www.palmeiras.com.br/calendario/">palmeiras.com.br/calendario</a> ·
    projeto não oficial, sem vínculo com o clube.
  </footer>
</main>
</body>
</html>
"""


# --------------------------------------------------------------------------- #
# Linha de comando
# --------------------------------------------------------------------------- #

def main() -> int:
    ap = argparse.ArgumentParser(description="Gera o .ics com os jogos do Palmeiras.")
    ap.add_argument("--saida", default="docs/palmeiras.ics", help="caminho do .ics")
    ap.add_argument("--index", default="docs/index.html", help="caminho da pagina (vazio para nao gerar)")
    ap.add_argument("--entrada", help="JSON local em vez da API (testes offline)")
    ap.add_argument("--ano", type=int, help="ano a assumir com --entrada")
    ap.add_argument(
        "--url-ics",
        default="https://guslfsantos.github.io/calendario-palmeiras/palmeiras.ics",
        help="URL publica do .ics, exibida na pagina",
    )
    args = ap.parse_args()

    hoje = dt.datetime.now(TZ).date()
    agora = dt.datetime.now(dt.timezone.utc)

    if args.entrada:
        dados = json.loads(Path(args.entrada).read_text(encoding="utf-8"))
        brutos = []
        if isinstance(dados, dict) and "meses" in dados:
            # {"meses": [{"ano": 2026, "mes": 10, "jogos": [...]}, ...]}
            for bloco in dados["meses"]:
                for jogo in bloco.get("jogos") or []:
                    if util(jogo):
                        brutos.append((jogo, int(bloco["ano"])))
        else:
            jogos = dados.get("jogos") if isinstance(dados, dict) else dados
            ano = args.ano or hoje.year
            brutos = [(j, ano) for j in jogos if util(j)]
        vistos: set[str] = set()
        unicos = []
        for jogo, ano in brutos:
            if str(jogo["id"]) in vistos:
                continue
            vistos.add(str(jogo["id"]))
            unicos.append((jogo, ano))
        brutos = unicos
    else:
        brutos = coletar(hoje)

    eventos = [montar_evento(jogo, ano) for jogo, ano in brutos]

    caminho_ics = Path(args.saida)
    anterior = caminho_ics.read_text(encoding="utf-8") if caminho_ics.exists() else None
    conferir(eventos, hoje, anterior)

    gravar_se_mudou(caminho_ics, montar_ics(eventos, agora))
    if args.index:
        gravar_se_mudou(Path(args.index), montar_index(eventos, hoje, args.url_ics))
    return 0


if __name__ == "__main__":
    sys.exit(main())
