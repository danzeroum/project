# ADR-029 — O atestado é o único conteúdo auto-mergeável, e o portão não julga os checks

**Status:** accepted · **Data:** 2026-08-05 · **Proposta:** CP-037
**Filho de:** ADR-028 (a autoridade externa está ligada) — resolve o atrito que ele criou

## Contexto

O ADR-028 ligou a autoridade e declarou o custo em voz alta: *"este repositório passa a depender
de um cron que não é dele; se a autoridade parar, o molde bloqueia em 25h."*

Ficou uma parte que ele não declarou, e que só aparece na operação: o cron **abre um PR**, e o PR
precisa de um clique. A trava passou a ter uma ação humana **diária** no caminho crítico.

Isso não é um inconveniente, é um modo de falha conhecido. Princípio (e) — *o custo do fiscal é
parte do fiscal*. Quem precisar integrar às 3h da manhã com o molde bloqueado por um atestado
vencido não vai admirar o desenho; vai procurar o caminho de menor resistência. E o caminho de
menor resistência de uma trava incômoda é desligá-la.

## Decisão

**O PR diário do atestado mergeia sozinho.** Três condições, todas necessárias:

| # | Condição | Quem confere |
|---|---|---|
| 1 | o diff contém **exclusivamente** o `attestation_path` | `ci/automerge_gate.py::decidir` |
| 2 | o autor é o App declarado em `authorized_issuer` | `ci/automerge_gate.py::decidir` |
| 3 | todos os checks obrigatórios passam | **o auto-merge nativo do GitHub** |

### A terceira não é nossa, e isso é a decisão

Seria fácil ler o estado dos checks num passo e mergear se estivessem verdes. Seria errado: esse
passo leria um estado **que ainda vai mudar** e depois mergearia com base nele. Um check que entra
em fila trinta segundos depois não existiria para ele.

`gh pr merge --auto` entrega a pergunta a quem tem a resposta. O GitHub segura o merge até os
required status checks e o ruleset passarem, e mergeia então — ou nunca, se reprovarem.

> **Auto-merge é dispensa de clique, jamais dispensa de validação.**

E por isso `--auto`, nunca `--admin`. `--admin` atropela o ruleset — a única coisa neste desenho
que o conteúdo de um PR não pode alcançar.

## `pull_request_target`, e por que essa linha é a segurança inteira

Com `pull_request`, o YAML executado vem do **head do PR**. Um PR que alterasse este workflow
rodaria a versão alterada: as checagens que decidem se ele pode auto-mergear seriam escritas por
ele mesmo.

Com `pull_request_target`, o workflow vem da **base**. E nenhum passo faz checkout do head nem
executa uma linha vinda dele — o que se lê do PR é **metadado da API** (autor e lista de caminhos),
nunca código. É a assimetria do ADR-025 outra vez: quem propõe não reescreve o que julga a
proposta.

## O que torna caro alargar isto depois

A comparação é uma **igualdade** contra uma lista de **um** caminho, lido de `harness.yaml`:

```python
if tocados != [caminho_atestado]:
```

Não é allowlist, não é prefixo, não é glob. A diferença é toda: um `startswith` teria exatamente o
mesmo efeito hoje e custaria **uma linha** para virar `harness/` amanhã. Acrescentar um segundo
caminho auto-mergeável exige mudar o núcleo, a asserção que o vigia e a mutação canônica que a
prova — três lugares, um PR, uma CP declarada.

## Recusar não é reprovar (princípio (h))

Um PR humano que toca o atestado é **legítimo**. Ele só não é auto-mergeável, e não deve ficar
vermelho por isso: o portão sai `0` e escreve no resumo do job por que o PR ficou para revisão.

O que sai diferente de `0` é a **indeterminação**: sem `authorized_issuer` ou sem
`attestation_path` declarados, o portão não sabe contra o que comparar. Exit `2` — "não foi
possível fiscalizar", o mesmo código do resto da casa. Um portão que não sabe comparar tem
exatamente uma resposta segura, e não é liberar.

E os motivos são **todos**, não o primeiro: um PR de humano que toca o atestado *e* mais um
arquivo tem dois problemas, e quem for lê-lo amanhã precisa dos dois.

## A janela, calculada

O cron roda às **06:17Z**; o atestado vale **25h**. O carimbo de hoje vence às 07:17Z de amanhã,
e o de amanhã nasce às 06:17Z — **uma hora de folga**, que é a margem que a diferença entre 25h e
24h compra. Ela existe para absorver a fila do runner e a duração dos checks, não para absorver um
humano dormindo.

Se um dia de cron for perdido, o molde **bloqueia** — e é isso que ele promete. O que esta decisão
garante é que ele **se destrava sozinho**: a execução seguinte abre um PR cujo conteúdo é o
atestado novo, os checks rodam contra o merge (que já contém o atestado novo) e passam, o
auto-merge integra. Nenhum humano no caminho, nem para bloquear, nem para destravar.

## O que esta decisão NÃO faz, e o que se descobriu ao tentar

Não habilita o auto-merge nativo no repositório. Isso é `Settings → General → Pull Requests →
Allow auto-merge`, uma caixa de admin, e **ela está desmarcada** — sondado em 05/08/2026, e o
achado mudou o desenho.

A primeira versão do passo reprovava o job em qualquer erro. Teria pintado de vermelho **todo** PR
de atestado até alguém marcar a caixa. Vermelho permanente é como um fiscal se torna ignorado
(ADR-019) — a mesma razão pela qual o achado de "auditoria desligada" é `info` e não bloqueante.

Então são duas falhas com duas reações:

| Falha | Reação | Por quê |
|---|---|---|
| `Allow auto-merge` desmarcado | `::warning::` com a ação exata, **job verde** | é capacidade que falta no ambiente, não defeito do PR; o fallback é o estado de ontem |
| qualquer outra | `::error::`, **job vermelho** | token sem escopo, PR em estado inesperado, API fora — o desenho não fez o que promete |

O caminho não classificado termina em `exit 1` de propósito: um `exit 0` no fim engoliria em
silêncio todo modo de falha que ainda não conhecemos.

Fiscalizado por: `ci/automerge_gate.py::decidir`,
`.github/workflows/atestado-automerge.yml`, `tests/governance/test_automerge_bites.py`
