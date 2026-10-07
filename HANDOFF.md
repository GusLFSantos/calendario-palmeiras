# Handoff — calendario-palmeiras

Documento para o próximo agente. Escrito em 07/10/2026.

## Objetivo

Publicar um calendário iCalendar com **todos** os jogos do Palmeiras (Paulistão, Brasileirão, Copa do Brasil, Libertadores), com horário correto, para o usuário assinar no Google Agenda. Repositório: `git@github.com:GusLFSantos/calendario-palmeiras.git` (vazio no GitHub até alguém empurrar).

## Por que não usar um feed de terceiros

O usuário já testou vários. Os problemas são estruturais, não escolha ruim:

- **fixtur.es** — não tem Campeonato Paulista. Oferece também uma agenda pública do Google (`7cpk6d97cjbiup9p2aamn270qg@group.calendar.google.com`), não verificada.
- **FootCal** (`footcal.cbdm.app/team/121/`) — era o melhor candidato: horários certos, UID por jogo, janela móvel de últimos 5 + próximos 10. Mas usa API-Sports e **errou a semifinal da Libertadores de 2026**: publicou 13/10 17h00 sem estádio, quando a Conmebol confirmou 14/10 21h30 no Maracanã em 21/09. Registros provisórios do provedor que nunca foram atualizados. Sintoma reconhecível: `LOCATION:None, None`.
- Smart Calendars AI (só liga, não time), Stanza, SportsCal, SportToCal — sem cobertura brasileira adequada.

Conclusão: todo feed público é revenda de um provedor de dados que carrega datas provisórias nos mata-matas. A única fonte que acerta é o próprio clube.

## A descoberta que viabiliza o projeto

O site do Palmeiras é WordPress e expõe uma **API REST pública, sem autenticação**:

```
https://www.palmeiras.com.br/wp-json/apiverdao/v1/jogos-mes?mes=MM&ano=AAAA
```

Um mês por chamada. Devolve `{"jogos": [...]}`. Varrendo os meses dá a temporada inteira: em 07/10/2026 havia 72 jogos entre dez/2025 e dez/2026, incluindo o Paulistão de janeiro a março com as duas finais.

(`/wp-json/toApp/v1/calendario` existe mas devolve 401. Não insista.)

### Campos usados

`id`, `time_casa`, `time_visitante`, `data_jogo` (`"14/10"`, **sem ano**), `hora` / `hora1` / `hora_alt`, `estadio`, `campeonato`, `rodada`, `excecao` (canais de TV), `placar_casa`, `placar_visitante`.

### Armadilhas da API — todas já tratadas em `scripts/gerar_ics.py`

1. **`hora1` é o horário LOCAL DO ESTÁDIO, não o de Brasília.** Em jogos fora do país o adversário vem com sufixo (`LDU-EQU`, `Cerro Porteño-PAR`, `Junior Barranquilla-COL`) e o horário tem que ser interpretado no fuso daquele país. Validado em três jogos: Junior/Barranquilla `19:30` com `hora_alt 21H30`, Sporting Cristal/Lima `17:00` com `hora_alt 19H00`, e LDU/Quito `17:00` sem `hora_alt` (API-Sports confirma 19h de Brasília). Quando `hora_alt` existe, é o mesmo jogo em horário de Brasília e serve de conferência — o script compara e avisa no stderr se discordarem.
2. **`00H00` significa "horário a definir"**, não meia-noite. Os jogos de 18/11, 21/11, 28/11 e 02/12 estão assim. Viram eventos de dia inteiro.
3. **Meses sem tabela publicada devolvem um registro-fantasma** com todos os campos `null` (visto em 2027). Filtrado por `util()`.
4. **`excecao` vem com HTML**: `<b>Globo e Premiere</b>`. Limpo por `limpar()`.
5. **`estadio` pode ser `null`.**
6. `data_jogo` não traz ano — vem do parâmetro da consulta, com tratamento da virada dez/jan.

## Estado atual

Um commit local, **não empurrado**. Tudo passa: `python tests/teste.py` → 29 testes ok.

```
scripts/gerar_ics.py              gerador (stdlib apenas: urllib + zoneinfo)
tests/teste.py                    29 testes, sem dependências
tests/fixtures/*.json             respostas reais da API, capturadas em 07/10/2026
.github/workflows/atualizar.yml   cron 2x/dia + workflow_dispatch, commita se mudou
.github/workflows/testes.yml      CI em push/PR
docs/.gitkeep                     Pages serve esta pasta; conteúdo é gerado
README.md                         instalação e manutenção
```

Decisões de projeto que valem preservar:

- **UID = `jogo-<id da API>@...`.** Mudança de horário *edita* o evento em vez de duplicar. É exatamente o erro do FootCal, cujo UID embute a data.
- **Falha alto, nunca publica lixo.** `conferir()` aborta sem gravar se extraiu menos de 5 jogos, se não há jogo futuro, se alguma data é implausível, ou se o total caiu a menos da metade do arquivo anterior. O workflow fica vermelho, o GitHub manda e-mail, e o `.ics` antigo continua no ar.
- **Saída idempotente.** `DTSTAMP` é ignorado na comparação, então execuções sem novidade não geram commit.
- Datas em UTC com `Z`; `REFRESH-INTERVAL` de 6h; linhas dobradas em 75 octetos conforme RFC 5545.

## O que falta

1. **Empurrar** (o usuário vai fazer, ou peça um PAT fine-grained com *Contents: write*):
   ```bash
   git remote add origin git@github.com:GusLFSantos/calendario-palmeiras.git
   git branch -M main && git push -u origin main
   ```
2. **Settings → Pages**: `Deploy from a branch`, `main`, pasta `/docs`.
3. **Actions → Atualizar calendário → Run workflow.** Essa é a **primeira execução real contra a API** — ver item "não verificado" abaixo. Confira no log a contagem por competição e se há avisos de fuso.
4. Conferir o `.ics` gerado: `https://guslfsantos.github.io/calendario-palmeiras/palmeiras.ics`. O jogo 5250 deve sair como `DTSTART:20261015T003000Z` (14/10 21h30 em Brasília).
5. **Assinar** no Google Agenda pelo navegador: Outras agendas → + → Do URL. Para o celular, marcar em `calendar.google.com/calendar/syncselect` — agenda assinada por URL não aparece no app sem isso.

## Não verificado

**O gerador nunca rodou contra a API de verdade.** O sandbox da sessão anterior não tinha saída de rede para `palmeiras.com.br` (proxy bloqueando), então toda a lógica foi desenvolvida e testada sobre fixtures capturadas via navegador. As funções `buscar_mes()` e `coletar()` são o único código sem cobertura de teste. A primeira execução do workflow é o teste real — acompanhe.

Se você tiver rede, vale rodar antes de empurrar:
```bash
python scripts/gerar_ics.py --saida /tmp/x.ics --index /tmp/x.html
```

## Riscos conhecidos

- **O GitHub desativa workflows agendados após ~60 dias sem atividade no repositório, e commits do próprio Actions não contam.** Chega e-mail de aviso antes; resolve-se clicando em *Enable workflow*, ou trocando o `GITHUB_TOKEN` por um PAT do usuário no passo de commit.
- O Google busca feeds externos no ritmo dele — horas, às vezes um dia. O arquivo fica correto 2x/dia; a agenda do usuário, com esse atraso. Se ele quiser propagação rápida, o caminho é escrever direto na API do Google Calendar (o conector existe no diretório, não estava conectado na conta dele).
- O parser depende do formato da API. Se o clube reformar o site, as travas fazem o workflow falhar em vez de publicar vazio — mas aí alguém precisa atualizar `tests/fixtures/` e o parser junto.
- **Janeiro de 2027 é o próximo ponto de atenção.** Em 07/10/2026 as consultas a 2027 vinham vazias (tabela não publicada). A janela do script vai de 2 meses atrás a 14 à frente, então os jogos aparecem sozinhos quando o clube publicar. Vale conferir em janeiro se o Paulistão 2027 entrou.
- O caminho de aviso quando `hora1` e `hora_alt` discordam nunca disparou com dados reais — os três casos conferidos concordaram.

## Preferências do usuário

Pediu explicitamente respostas **claras e breves**, sem linguagem informal e sem tom paternalista.
