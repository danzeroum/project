# ADR-019 — O vermelho durante mudança declarada é mapa, não defeito

**Status:** accepted · **Data:** 2026-08-05 · **Proposta:** CP-029 · **Origem:** Adendo A ao plano v2.2, §A1

## Contexto

Uma pergunta reaparece toda vez que alguém novo olha esta harness: *por que uma mudança grande de
negócio, arquitetura ou governança não se propaga sozinha pelos metadados?* O repositório sabe que
`CAP-001` é referenciada por regras, requisitos, componentes e superfícies. Por que, ao mudar
`CAP-001`, ele não atualiza os dependentes?

A pergunta ganha força quando se vê o repositório **vermelho** no meio de um pivô. Vermelho parece
defeito. E a conclusão natural — "falta automação de cascata" — já foi proposta duas vezes na
revisão deste plano, por caminhos diferentes (R-01, R-03).

## Decisão

**Não há propagação automática, e isso é a decisão — não uma lacuna.**

A harness separa decisão de execução. A mudança é declarada e aprovada numa change-proposal;
**pessoas ou agentes** aplicam as edições sob essa CP; os fiscais verificam se as relações
declaradas continuam coerentes. `validate_all.py` não decide o novo significado do negócio — ele
aponta quais contratos declarados deixaram de ser verdadeiros.

**Esse vermelho é o roteiro de impacto.** Cada inconsistência exige que alguém decida se adapta,
aposenta, substitui ou justifica a relação afetada. A automação fica restrita ao que é
mecanicamente derivável.

A promessa correta não é *"mudou uma coisa, a harness atualiza tudo"*. É:

> **"mudou uma decisão importante, a harness impede que as consequências declaradas dessa decisão
> fiquem ocultas ou inconsistentes."**

### Por que a alternativa é pior

Um propagador automático precisaria decidir, sem contexto, se `CAP-001` mudar de escopo significa
que a regra que a cita deve ser reescrita, aposentada ou mantida. Ele escolheria uma dessas — e
escolheria em silêncio. O resultado seria um repositório **verde** com metadados que ninguém
julgou: a forma mais cara de mentira, porque parece exatamente com a verdade.

O vermelho é caro e visível. O verde falso é barato e invisível. Entre os dois, este repositório
escolhe o caro e visível, sempre.

### O fluxo de um pivô

1. **Declarar** — CP de risco `high` listando as `CAP-*`/`CMP-*` afetadas; aval humano resolvível
   por review real (ADR-016) é pré-condição.
2. **Editar a fonte e expor o vermelho deliberado** — `validate_all.py` reporta as referências e
   relações que ficaram inválidas. Esse vermelho é o mapa.
3. **Executar a cascata sob a CP** — por agentes ou pessoas. A harness valida o resultado; ela não
   toma decisões semânticas nem as aplica autonomamente. Não há orquestrador em runtime, por
   desenho (coerente com R-03). O fiscal sugere o comando; jamais o executa (fronteira do R-01).
4. **Regenerar apenas o derivado** — hoje `docs/metadata-graph.md` e `docs/alignment.md`, conferidos
   por `--check`. Fonte de verdade se edita com revisão; artefato derivado se regenera sem pedir
   licença.
5. **Decisão estrutural vira ADR com supersedência declarada** — o ADR antigo fica com
   `status: superseded`, não é apagado, e a asserção antiga é trocada pela nova, de modo que o CI
   policie a arquitetura nova imediatamente.

### Os três amortecedores

O que torna esse fluxo barato:

**(i) Arestas por ID, não por caminho** — `CAP-001` continua sendo `CAP-001` onde quer que o
arquivo more; reorganização estrutural não quebra referência.

**(ii) Maturidade permite transição honesta** — rebaixar para `proposed` isenta de código e teste,
e o repositório fica verde **dizendo a verdade** ("em transição") em vez de vermelho por semanas ou
verde mentindo. É o que torna um pivô fatiável: a fatia 1 rebaixa e fica verde-honesta, as
seguintes elevam de volta conforme entregam.

**(iii) Reancoragem deliberada para o caso extremo** — quando o que os metadados descrevem muda de
alvo, isso é uma CP própria, com o risco declarado de que todo `source_path`/`verified_by` passa a
resolver contra outro código.

Até o CP-029 esses três eram propriedades **emergentes** do desenho dos schemas: nenhum fiscal os
garantia genericamente. Propriedade emergente sem asserção é propriedade que o primeiro refactor
grande destrói sem avisar — e destrói exatamente durante o pivô, que é quando ela importa. O
CP-029 as transforma em asserção.

### Fatiamento

Pivô grande se **fatia**. Monolito só quando uma fatia não consegue ficar verde-honesta isolada.
O que torna cada fatia mergeável sozinha é o amortecedor (ii).

*Lacuna registrada:* o schema da CP ainda não tem vínculo formal entre fatias — um campo
`part_of`/`parent_cp` entra na mesma iteração futura já adiada do grafo de decisões, junto com
`supersedes`.

## Consequências

Quem vê este repositório vermelho durante uma CP `high` aberta está vendo o sistema funcionar, não
falhar. O fiscal de atrito captura esse vermelho transitório e o associa ao ID da CP — se a mesma
capacidade aparece como ponto de quebra em CPs consecutivas de natureza diferente, o mal-fatorado é
a capacidade, não as CPs que a tocam.

Este ADR existe para que "automatizar a cascata" não seja proposto uma terceira vez sem enfrentar
o registro. Dois revisores independentes chegaram a ele por caminhos diferentes — sinal usual de
decisão madura para registro.

## Fiscal

Os três amortecedores: `ci/audit_governance.py::check_references_by_id`, `::check_maturity_gates`
e `::check_derived_vs_source`. A ausência de propagação automática é, por natureza, uma asserção
`manual` — não se verifica por máquina que algo NÃO foi construído; o que se verifica é que os
amortecedores que a tornam viável continuam mordendo.
