# ADR-031 — O relatório é derivado, deriva tudo e não conhece alvo nenhum

**Status:** accepted
**Data:** 2026-08-07
**Proposta:** `harness/change-proposals/CP-045-relatorio-derivado.yaml`

## Contexto

Acompanhar este repositório exige hoje abrir 28 YAMLs e rodar onze fiscais. Não existe uma vista
que responda "o que este repositório é, o que ele governa, o que está coberto, o que ficou aberto
e com que prazo" sem tradução manual — e tradução manual é a coisa que este repositório inteiro
existe para recusar.

A tentação óbvia é escrever essa vista. É a decisão errada, e o repositório já tem a prova do
porquê dentro dele: **`CLAUDE.md` afirma "as treze etapas" enquanto `harness/stages.yaml` declara
catorze.** O texto passou a mentir na etapa que alguém acrescentou sem reler a prosa. Ninguém
percebeu porque nada o fiscalizava, e o texto continua parecendo documentação cuidadosa.

Uma tela de relatório tem vinte lugares onde esse mesmo defeito cabe.

## Decisão

O relatório é um **artefato derivado**, gerado por `ci/generate_report.py`, mantido em dia pelo
`--check` e regido por três invariantes:

**1. Ele não contém a informação, ele a deriva.** Nenhuma lista escrita à mão, nenhum identificador
literal, nenhum contador escrito na tela. Todo número é `len()` de uma coleção real; toda coleção
vem de um caminho declarado. O gerador importa `harness_lib` e **não** reimplementa leitura de
YAML: um segundo leitor produziria uma segunda resposta para a mesma pergunta.

A armadilha aqui é auto-referente e vale registrar: acrescentar este próprio gerador a
`validate_all.py::_steps()` mudou o número de fiscais. Um contador escrito na tela nasceria errado
no primeiro commit da mudança que o criou.

**2. Nenhum alvo é especial.** Zero nomes de negócio, zero nomes de derivado, zero identificadores
literais no gerador. O teste que prova não é de estilo: rodado contra um repositório sem o negócio
de exemplo, o gerador produz relatório vazio e coerente, exit 0.

E o vazio tem três estados que nunca se pintam iguais — `declarado vazio`, `ainda não ingerido`,
`não consegui ler`. Pintá-los juntos é a família de defeito da CP-040, e num derivado recém-criado
quase tudo cai no segundo caso.

**3. O gerador nunca publica, e o inventário nunca sai em claro por padrão.** Publicar é passo de
workflow que alguém liga. Quando o destino for público, `--redigir` troca os campos do inventário
de dado pessoal por contagens. Um HTML publicado com o inventário de um derivado não vaza o dado do
titular: vaza o **mapa de onde ele está**.

## Consequências

O `--check` entra em `_steps()` e passa a reprovar artefato desatualizado ou editado à mão. Fonte
ilegível sai **2** (`FISCAL_CEGO:`), nunca 0 — "não sei olhar" não pode sair igual a "nada a ver".

A procedência é o `sources_digest`, não o SHA do commit. Embutir o `HEAD` tornaria o artefato
diferente a cada commit: gera, commita, o `HEAD` muda, o `--check` reprova, regenera — o laço que
transforma a trava em ruído que as pessoas desligam. O digest é determinístico e mais preciso: dois
commits que não tocam metadado têm o mesmo digest, e é isso que se quer comparar.

Publicar cria superfície web, o que torna falso o `not_assessed` do parecer de privacidade. O
parecer é refeito no mesmo PR — deixar para depois deixaria o repositório vermelho no meio, que é
como um fiscal aprende a ser ignorado.

## Sobre a asserção que recusa identificador literal

`ADR-031-A3` ancora o padrão em **aspas** (`['"][A-Z]{2,}-...`), e a escolha é deliberada. Um padrão
cru acusaria os comentários deste próprio gerador, que citam `CP-040` e `RISK-INCUBA-001` para
explicar por que as regras existem — a família âncora-na-menção que `harness/policies/conformance.md`
registra com nove ocorrências, a última nascida dentro do fiscal escrito para vigiar as anteriores.

Proibir a explicação onde o próximo leitor procura o porquê seria pagar o custo da trava e perder o
benefício dela. O que a asserção recusa é identificador usado como **dado**; o que ela permite é
identificador usado como **razão**. `tests/governance/test_relatorio_bites.py` faz a verificação
rigorosa por AST, sobre constantes de string em código executável.
