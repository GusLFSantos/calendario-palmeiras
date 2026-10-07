# calendario-palmeiras

Calendário público com **todos** os jogos do Palmeiras — Paulistão, Brasileirão, Copa do Brasil, Libertadores — em formato iCalendar, para assinar no Google Agenda, Apple Calendar ou Outlook.

A fonte é a API pública do próprio site do clube, que é a única que acerta data e horário das fases finais. Um workflow do GitHub Actions regenera o arquivo duas vezes ao dia e o GitHub Pages o serve.

**URL para assinar:**

```
https://guslfsantos.github.io/calendario-palmeiras/palmeiras.ics
```

## Instalação

1. `git push` deste repositório para `main`.
2. **Settings → Pages**: em *Source* escolha `Deploy from a branch`, branch `main`, pasta `/docs`.
3. **Actions → Atualizar calendário → Run workflow**. Essa primeira execução cria `docs/palmeiras.ics` e `docs/index.html`.
4. No Google Agenda (navegador, não o app): **Outras agendas → + → Do URL**, cole a URL acima.
5. Para ver no celular, marque a agenda em [calendar.google.com/calendar/syncselect](https://calendar.google.com/calendar/syncselect) — agendas assinadas por URL não aparecem no app sem isso.

## Como funciona

A API devolve um mês por chamada:

```
https://www.palmeiras.com.br/wp-json/apiverdao/v1/jogos-mes?mes=10&ano=2026
```

O script varre de 2 meses atrás até 14 meses à frente, junta tudo, descarta duplicatas pelo `id` do jogo e grava o `.ics`. Duas decisões importam:

**UID estável.** Cada evento usa o `id` do jogo na API (`jogo-5250@...`). Quando a Conmebol ou a CBF muda o horário, o evento é *editado* no seu calendário, em vez de aparecer duplicado ao lado do antigo.

**Fuso do estádio.** A API grava o horário **local do estádio**, não o de Brasília. Quando o Palmeiras joga fora do país, o adversário vem com sufixo (`Cerro Porteño-PAR`, `LDU-EQU`) e o horário é interpretado no fuso daquele país antes de virar UTC. Conferido contra três jogos de 2026: Junior/Barranquilla, Sporting Cristal/Lima e LDU/Quito. Quando a API também preenche `hora_alt` (o mesmo jogo em horário de Brasília), o script compara as duas e avisa no log se discordarem.

`00H00` na API significa "horário a definir", não meia-noite: esses jogos entram como evento de dia inteiro e ganham horário quando a entidade confirmar.

## Quando algo quebra

O script **falha em vez de publicar lixo**. Ele aborta sem gravar nada se:

- extraiu menos de 5 jogos (a API provavelmente mudou de formato);
- não há nenhum jogo futuro na lista;
- alguma data está fora de uma janela plausível;
- o total caiu para menos da metade do arquivo anterior (resposta parcial da API).

Nesses casos o workflow fica vermelho e o GitHub manda e-mail — o `.ics` antigo continua no ar, correto, até alguém olhar. Isso é de propósito: um calendário silenciosamente vazio é pior do que um calendário velho.

## Manutenção

**O GitHub desativa workflows agendados após ~60 dias sem atividade no repositório, e commits feitos pelo próprio Actions não contam como atividade.** Você recebe um e-mail de aviso antes; basta clicar em *Enable workflow*. Para evitar de vez, troque o `GITHUB_TOKEN` padrão por um PAT seu no passo de commit.

O Google busca feeds externos no ritmo dele — normalmente algumas horas, às vezes um dia. O arquivo fica correto duas vezes ao dia; a sua agenda, com esse atraso.

## Desenvolvimento

```bash
python tests/teste.py                          # testes, sem dependências
python scripts/gerar_ics.py                    # busca na API e grava em docs/
python scripts/gerar_ics.py \
  --entrada tests/fixtures/casos-limite.json \
  --saida /tmp/teste.ics --index ""            # offline, sobre fixtures
```

As fixtures em `tests/fixtures/` são respostas reais da API, capturadas em 07/10/2026. Se a API mudar, atualize-as junto com o parser.

## Aviso

Projeto não oficial, sem vínculo com a Sociedade Esportiva Palmeiras. Faz duas requisições por dia ao site do clube, identificadas por User-Agent. Os dados são do clube; o código é livre.
