---
name: desenvolver
description: Orienta o desenvolvimento neste repositório — onde você está, o que muda junto com o quê, quais fiscais rodam em cima da mudança e o que já está vermelho. Use SEMPRE ao começar a trabalhar aqui, ao receber uma tarefa que toca metadado, código, schema, fiscal ou governança, e antes de abrir qualquer change-proposal. Use também quando um fiscal reprovar e você não souber por quê, ou quando o repositório governar um alvo clonado em workspace/target/ e você precisar saber quanto da ingestão falta.
---

# Desenvolver neste repositório

Esta página **não lista** as etapas, os fiscais nem os caminhos. Ela manda você perguntar — porque
uma lista escrita aqui derivaria de `harness/stages.yaml` em silêncio, com a aparência de
documentação cuidadosa, e passaria a ensinar um repositório que não existe mais. É o ADR-002
aplicado à própria orientação, e `ADR-014-A3` reprova o CI se alguém escrever um id de etapa aqui.

## 1. Antes de qualquer coisa

```bash
python ci/orient.py
```

Responde: qual o papel do repositório, qual alvo ele governa e em que commit, quais dos fiscais
estão vermelhos **agora**, quanto do código já tem dono, e qual é o próximo passo.

Se ele disser que não deu para orientar, a resposta é `python ci/bootstrap.py` — não improvisar.

## 2. Antes de editar

```bash
python ci/orient.py --tocar <caminho>...
```

Para cada caminho: a etapa dona, os fiscais que vão rodar, a pergunta de privacidade daquela
etapa, e se é `protected_path` — caso em que a mudança **começa por uma change-proposal** em
`harness/change-proposals/` (ADR-004), não por uma edição.

Caminho que ainda não existe também é resposta útil: ele avisa que nenhuma etapa o reivindica, e
a partição vai reprovar até alguém declarar a que etapa ele pertence.

## 3. Antes de encerrar

```bash
python ci/validate_all.py
```

`0` conforme · `1` divergência entre o declarado e o real · `2` algum fiscal não conseguiu
fiscalizar. É exatamente o que o CI roda.

## As quatro coisas que se erra aqui

**Editar um artefato derivado.** `docs/metadata-graph.md` e `docs/alignment.md` são gerados. O
hook nega a escrita e o `--check` do CI contradiz qualquer edição manual. Regerar é a correção.

**Afrouxar um fiscal para o CI passar.** Se um fiscal acusa, ou o repositório está errado, ou a
decisão precisa mudar explicitamente — por ADR novo, não por silêncio. Editar o fiscal é a
terceira opção, e é a errada.

**Criar metadado novo pela metade.** Todo YAML de metadado custa quatro coisas, e `CLAUDE.md` diz
quais. Pagar três e não a quarta deixa o repositório verde e a cobertura falsa.

**Preencher julgamento no lugar de quem julga.** `risk_level`, `likelihood`, `impact` e base legal
são de humano. Máquina escreve `pending_judgment`, que é recusado em documento promovido.

## Quando o repositório governa um alvo

O código do alvo vive em `workspace/target/`, materializado no commit de `target.lock`, e **não é
versionado aqui** — o derivado declara o alvo, nunca o copia. O alvo é lido; nada neste
repositório escreve nele.

`python ci/orient.py` mostra quantos arquivos do alvo ainda estão órfãos. Esse número é o trabalho
de ingestão que falta, e ele chega a zero por `/ingerir`, não por isenção.

## Onde ler mais, quando a orientação não bastar

`BOOTSTRAP.md` (porta de entrada) · `CLAUDE.md` (doutrina e as regras de custo) ·
`harness/policies/` (cada regra e seu fiscal) · `architecture/adr/` (as decisões e suas
asserções) · `docs/alignment.md` (o que ficou de fora).
