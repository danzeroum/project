# ADR-031 — O painel de configuração deriva dos contratos, e prova isso a cada execução

**Status:** accepted · **Data:** 2026-08-07 · **Proposta:** CP-050

## Contexto

A pergunta *"o que já está decidido antes de eu chegar?"* tem resposta completa e correta neste
repositório, distribuída por trinta e um contratos em `harness/schemas/`. É o formato certo para
uma máquina julgar e o errado para uma pessoa se orientar: ninguém abre trinta arquivos para
descobrir quais valores `risk.status` aceita ou por que `kind: mold` proíbe o bloco `target`.

Construir a tela que responde isso é a maior exposição ao `RISK-ORIENT-001` que este repositório
já teve — *orientação que enumera em vez de derivar* —, e o modo de falha aqui é pior do que na
tela de conteúdo. **Um dado velho às vezes é visivelmente velho; um vocabulário velho não é.**

Se alguém escrevesse a lista de valores de `risk.status` dentro do gerador, e amanhã o contrato
ganhasse um valor novo, a tela continuaria renderizando **perfeita** — sem erro, sem aviso, sem
nada ficar vermelho — ensinando um vocabulário que o repositório já não usa. É a segunda descrição
que o `ADR-014` nomeia, na forma mais difícil de perceber: a que não quebra.

Havia ainda a armadilha que o próprio trabalho arma. Acrescentar este gerador ao agregado de
`ci/validate_all.py` **muda o número de fiscais**. Qualquer número escrito na tela sobre o
repositório passa a mentir no dia seguinte ao merge — e o primeiro a mentir seria justamente o
desta mudança.

## Decisão

**Tudo que a tela mostra nasce de uma travessia dos próprios contratos, no instante da geração. E
o gerador prova isso a cada execução, lendo o próprio AST.**

Quatro consequências, todas verificáveis:

1. **Zero transcrição.** Nenhum valor de vocabulário, forma de identificador, valor travado ou
   contagem é literal em `ci/generate_config_report.py`. Toda contagem é `len()` de coleção
   derivada, inclusive a de fiscais agregados, que é lida por AST do `return` de `_steps()`.

2. **Deduplicação por JSON Pointer, nunca por valor.** A mesma escala de rótulos aparece em vários
   contratos significando coisas diferentes — severidade de asserção, criticidade de negócio,
   nível de risco de proposta. Fundi-las apagaria exatamente a informação de que são escalas
   distintas, que é o que o leitor precisa ver.

3. **A autoauditoria lê o AST, não o texto.** Um arquivo que fala *sobre* vocabulário fechado
   contém as palavras do assunto em toda parte, inclusive nos comentários que explicam por que ele
   não deve conter os *valores*. Procurar no texto cru ancoraria na menção — a família reincidente
   registrada em `harness/policies/conformance.md`, cuja última ocorrência nasceu *dentro* do
   fiscal escrito para vigiar as anteriores. No AST, comentário não existe.

4. **O artefato conferido é função pura do conteúdo da árvore.** Sem `datetime.now()`, sem branch,
   sem commit SHA. Um SHA embutido faria o `--check` reprovar para sempre: o artefato nasce num
   commit e é conferido no seguinte, então o valor mudaria sem que o conteúdo mudasse. A
   procedência é `inputs_fingerprint` — impressão do conteúdo de tudo que foi lido —, e o carimbo
   volátil vai para o laudo sob `harness/reports/`, por onde nenhum fiscal caminha.

### O que a decisão custou, e por que o custo é o ponto

Na **primeira execução**, a autoauditoria reprovou o próprio gerador. Cinco literais em posição de
dado, e nenhum deles era descuido óbvio: dois eram valores do vocabulário do *próprio* artefato
(os estados de coleção vazia), um era o rótulo de ciclo de vida usado numa comparação, um era o
status de régua usado para decidir se `entrypoint` estava proibido, e um era um nome de protocolo
que também é valor de enum em outro contrato.

Os quatro primeiros viraram derivação: os estados de vazio passaram a ser lidos do contrato por
ponteiro **nomeado**; a decisão de "ainda não ingerido" passou a olhar se o artefato declarado
como saída da ingestão existe no disco, em vez de olhar um rótulo; e os status que proíbem
`entrypoint` passaram a ser lidos da própria trava que os proíbe. O quinto foi renomeado.

Nenhum virou exceção, e isso é a decisão dentro da decisão: **lista de exceção é o buraco que este
desenho existe para não ter.** Se um literal interno colidir com um valor de vocabulário, o
conserto é renomear a string interna.

### O que se recusou

- **Glosa paralela para a prosa das travas.** Quase todo bloco condicional deste repositório já
  traz `comment`, e o que falta é sintetizado da estrutura por template. Uma glosa chaveada por
  JSON Pointer apodrece assim que um ponteiro se move, e custaria schema, entrada em `DOCS`,
  etapa, política e um fiscal de entrada órfã — para guardar texto cujo lugar certo é o contrato.
- **Asserção de texto procurando valor de vocabulário no gerador.** Ancoraria na menção. A
  verificação real roda dentro do gerador, e a asserção `ADR-031-A4` prova que ela continua lá.
- **Exemplo sintético para as formas de identificador.** O exemplo sai de uma instância que existe
  neste repositório, com o arquivo de onde saiu, ou a coluna some. Um exemplo que casa a regex mas
  não existe aqui é a segunda descrição em miniatura.
- **Node, bundler e CDN.** O `ADR-009` recusou exigir Node para fiscalizar um alvo qualquer, e um
  painel que busca fonte na rede some quando a rede some — em silêncio, porque a página ainda
  abre. A degradação para `system-ui`/`ui-monospace` é aceita e está escrita na política.

## Consequências

O painel reflete o estado vivo dos contratos: acrescentado um valor, uma trava ou um fiscal, ele
aparece **sem uma linha de alteração**; removido, some. As duas mordidas de classe
(`enum novo aparece sozinho` e `trava nova aparece sozinha`) exigem, além disso, que os **bytes do
gerador permaneçam inalterados** — sem essa segunda asserção elas só provariam que o pipeline
rodou.

Um contrato novo que não caia num grupo temático, e uma variável negada que caia fora das famílias
declaradas, **abortam com exit 2**. Não 1: exit 1 significa "regenere", e regenerar não classifica
um contrato novo. Exit 2 é literalmente verdade — o fiscal não sabe onde pôr a coisa. A entrada
morta acusa igual à faltante, pela razão de sempre: um mapa que guarda contrato apagado faz a
classificação parecer completa por um motivo que já não existe.

`ci/audit_governance.py::geradores_declarados` passou a reconhecer `docs/**/*.html`. Enquanto só o
markdown era reconhecido, um artefato derivado em HTML escapava inteiro da cobertura
"derivado sem fonte" — o mesmo buraco silencioso noutro formato, e num formato mais provável de
alguém abrir e editar à mão.

**Custo declarado:** o `--check` deste artefato é sensível a toda a superfície de configuração,
então mudanças em `ci/`, `harness/` e `.claude/` passam a exigir regeneração no mesmo commit. É o
preço de o artefato não poder envelhecer mentindo, e é o mesmo preço que `docs/metadata-graph.md` e
`docs/schema-reference.md` já cobram.
