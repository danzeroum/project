# ADR-028 — A autoridade externa está ligada, e o emissor é conferido

**Status:** accepted · **Data:** 2026-08-05 · **Proposta:** CP-036
**Fecha:** ADR-020 (a camada local não equivale à externa) — a lacuna que ele registrou

## Contexto

O ADR-020 disse o que faltava com precisão suficiente para ser cobrado:

> A camada local mora no mesmo repositório que fiscaliza: um PR com privilégio suficiente remove o
> passo e a asserção que o vigia **no mesmo commit**, e o CI fica verde porque a trava saiu junto
> com quem reclamaria dela.

`external_audit.enabled: false` existia para que essa lacuna aparecesse a cada execução em vez de
sumir. Ela apareceu por dez meses de calendário e três CPs. O que mudou hoje não foi uma decisão de
escrever mais código — o código estava escrito desde a CP-024. Foi a autoridade **passar a existir**:

| Peça | Onde | Por que conta como externa |
|---|---|---|
| verificador | `danzeroum/harness-authority` | repositório que este aqui não alcança: nenhum workflow, token ou PR deste lado o edita |
| identidade | GitHub App próprio | credencial que não é o `GITHUB_TOKEN` deste repositório |
| cadência | cron diário + atestado de 25h | uma execução perdida faz o atestado expirar, em vez de continuar valendo |
| objeto auditado | rulesets de `main` e de `refs/tags/v*` | a configuração real do servidor, lida de fora |

## Decisão

**`external_audit.enabled: true`.** O atestado passa a ser exigido: ausente, ilegível, fora do
schema, expirado ou de emissor não declarado **bloqueia** merge em caminho protegido e release.

E, no mesmo movimento, **`authorized_issuer` passa a ser declarado e conferido**. As duas coisas
andam juntas por uma razão que não é estética:

> Ligar sem conferir o emissor produziria "alguém atestou", não "quem devia atestou".

Um molde que exige atestado e aceita qualquer um é **pior** que um molde com a camada desligada.
Desligada, a lacuna está escrita e datada. Ligada-sem-emissor, ela está escondida atrás de um
arquivo JSON que quem tem direito de merge escreve à mão em trinta segundos — e o CI fica verde
com convicção.

O schema torna a combinação **inexpressável** em vez de proibida:

```json
{ "if":   {"properties": {"enabled": {"const": true}}, "required": ["enabled"]},
  "then": {"required": ["authorized_issuer"]} }
```

Proibir por texto exigiria alguém ler o texto. Assim, `enabled: true` sem emissor não é um
repositório errado — é um documento que não valida.

## Três estados, três achados (princípio (h))

Ausente, expirado e emissor-não-autorizado **não colapsam**:

| Achado | O que aconteceu | Para onde olhar |
|---|---|---|
| `EXT-AUDIT-SEM-ATESTADO` | o verificador não entregou | o cron da autoridade, ou a credencial dele |
| `EXT-AUDIT-ATESTADO-EXPIRADO` | ele entregou, e envelheceu | quantas execuções foram perdidas, e por quê |
| `EXT-AUDIT-EMISSOR-NAO-AUTORIZADO` | **alguém escreveu isso à mão** | o histórico do arquivo, e quem o tocou |

Os dois primeiros são falhas de operação. O terceiro é uma acusação. Um `EXT-AUDIT-INVALIDO`
genérico economizaria umas quinze linhas e destruiria exatamente a informação que faz alguém saber
qual dos três investigar.

E eles **não se excluem**: a checagem de emissor não tem `return`, então um atestado expirado *e*
de emissor errado produz **dois** achados — porque são dois problemas, e consertar um não conserta
o outro.

## O eixo de tags fica bloqueante sem uma linha de código nova

A CP-031 escreveu `verify_tag_protection` de modo que `external_audit.enabled` decide se as lacunas
**reportam** ou **bloqueiam**. Ligar a flag exerce esse desenho — e exercê-lo é o teste dele. Uma
decisão que se aplica sem editar código era decisão; uma que exige reescrever o fiscal era intenção.

## O que esta decisão NÃO faz

**Não torna o check da autoridade obrigatório no ruleset da `main`.** Esse passo é administrativo,
mora fora deste repositório, e é o que separa "o CI reprova" de "o merge é impossível". Ele é
desejável e está registrado — mas condicionar o verde desta decisão a uma configuração que este
repositório não controla repetiria o erro que congelou a `main` mais cedo hoje: exigir do
repositório uma condição que ninguém aqui consegue satisfazer produz vermelho permanente, e
vermelho permanente é como um fiscal se torna ignorado (ADR-019).

**Não fecha o `RISK-CHANGE-002`.** Aquele risco é sobre gente — não há segundo humano com direito
de review — e nada aqui o toca. Ele fica `open`, com `due: 2026-11-03`.

## O que passa a ser impossível em silêncio

Antes: apagar o ruleset de tags deixava o CI verde. A camada local não olha rulesets, e a externa
estava desligada.

Agora: a proteção real é lida de fora todo dia, e o carimbo vale 25 horas. Desligar a proteção
passa a ter **prazo de validade de um dia** para ser notado — sem depender de ninguém perceber.

## O custo, declarado (princípio (e))

**Este repositório passa a depender de um cron que não é dele.** Se a autoridade parar, o molde
bloqueia em 25h. Isso é o efeito desejado, não um efeito colateral: a alternativa a "bloquear
quando não sei" é "seguir verde sem saber", e é ela que este ADR inteiro existe para recusar.

O `accepted_risk` continua declarado em `harness.yaml` mesmo com o risco `mitigated`. Ele nomeia
**qual risco esta camada cobre** — e a trava de schema que o exige (ADR-020-A3) continua valendo
para o dia em que alguém puser a flag de volta em `false`.

## Como isto se prova

Cinco asserções, e duas delas existem por causa de uma mutação que não podia ser escrita antes.

O inverso canônico de toda mutação existente é **apagar**: o caminho some, o padrão some, o
ponteiro some. Nenhuma delas exprime o gesto que importa aqui. Apagar a linha `enabled: true`
produz **erro de schema** — um terceiro estado, com outra reação. Quem desliga a autoridade não
apaga a linha: escreve `false`, e o documento continua perfeitamente válido.

Por isso `substituir_texto` entrou em `ci/audit_mutations.py`. Ele muta até o estado que **não é
erro**, que é o único que prova que a asserção pega o gesto real em vez do desleixo.

Fiscalizado por: `ci/audit_governance.py::check_external_attestation`,
`ci/audit_mutations.py`, `harness/schemas/harness.schema.json`
