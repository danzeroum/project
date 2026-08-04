# ADR-010 — A ingestão declara de onde tirou cada coisa, e não julga o que tirou

- **Status:** accepted
- **Data:** 2026-08-04
- **Riscos relacionados:** RISK-INGEST-001, RISK-INGEST-002

## Contexto

O ADR-009 fechou a direção que faltava: código sem metadado reprova. O efeito colateral é que um
derivado recém-criado nasce **vermelho** — o alvo inteiro é órfão até alguém escrever componente
por componente. Fazer isso à mão num alvo real é trabalho de dias, e o que não se faz à mão fica
sem fazer: a invariante viraria uma trava que todo mundo aprende a contornar declarando isenções.

Automatizar resolve o volume e cria um problema pior. A premissa desta casa é que **o projeto
declara** e o padrão fiscaliza. Um pipeline que escreve declarações inverte isso em silêncio: o
metadado passa a existir sem que ninguém o tenha afirmado, e como ele *parece* declarado —
mesmo formato, mesmos schemas, mesmo diff — nenhum fiscal consegue distinguir o que um humano
decidiu do que uma heurística chutou.

Duas perguntas ficam sem resposta se a ingestão for ingênua. **De onde veio isto?** Um `CMP-*`
proposto a partir de um arquivo do alvo, sem dizer qual arquivo e em que commit, é uma afirmação
que ninguém consegue reconferir. **Quem decidiu que é alto risco?** Se a máquina preencher
`risk_level`, o julgamento entra vestido de humano e nunca mais é revisitado.

## Decisão

**1. Proveniência obrigatória e ancorada.** Todo item ingerido carrega
`derived_from: {repo, sha, path, section}`. O fiscal cobra três igualdades: `repo` é o alvo
declarado, `sha` é **exatamente** o de `target.lock`, `path` existe no alvo materializado.

A igualdade de SHA é o ponto. Sem ela, "este metadado descreve o alvo" degrada em silêncio para
"descrevia o alvo em algum momento" — o mesmo modo de falha que `target.lock` resolve uma camada
abaixo, e aqui pior, porque o metadado parece atual.

**2. `pending_judgment` como sentinela reprovável.** A ingestão não decide `risk_level`,
`likelihood`, `impact`, base legal, finalidade nem criticidade. Escreve o sentinela, e
`check_pending_judgment` o recusa em qualquer documento com `source_of_truth: true`.

É o inverso do `to-be-assessed` que o ADR-002 e o `CLAUDE.md` proíbem: aquele é um campo **aberto**
que nenhum fiscal consegue reprovar, e por isso a pendência vira permanente sem nunca aparecer
como falha. Este é **reprovável por construção** — só sobrevive enquanto o documento se declara
derivado. Promover é substituir o sentinela, não redeclarar o cabeçalho.

**3. O alvo é lido, nunca escrito.** Nenhuma fase cria branch, commit, issue ou PR lá.
`check_ingest_pipeline` reprova `outputs` apontando para `workspace/`.

**4. O pipeline é índice fiscalizado, não roteiro em prosa.** `harness/pipeline/ingest.yaml`
declara fases com `inputs`, `outputs`, `agent` e `fiscal` resolvível — pela **mesma** função que
resolve os fiscais de `stages.yaml`, porque duas implementações de "esse fiscal existe?"
divergiriam. Fase que escreve julgamento ou promove metadado tem `gate: human_approval`.

## Consequências

- Ingerir deixa de ser um passo e passa a ser oito, com dois gates humanos. É mais lento de
  propósito: o gargalo é o julgamento, e acelerá-lo é acelerar exatamente a parte errada.
- Um item ingerido e depois esquecido fica **detectável**: quando o lock avança, seu
  `derived_from.sha` deixa de casar e o fiscal acusa. É o insumo do `/sincronizar`.
- `pending_judgment` entra em enums que eram fechados (`risk_level`, `likelihood`, `impact`).
  Enum fechado ganhando valor novo merece desconfiança — a diferença aqui é que este valor tem um
  fiscal dedicado a expulsá-lo, e não existe caminho em que ele sobreviva num documento promovido.
- Custo assumido: o `cartographer` vai errar fronteira de componente, principalmente em monorepo.
  Aceitável porque a proposta vai por change-proposal e o erro fica visível no diff com a
  proveniência ao lado. Inaceitável seria o mesmo agente atribuir `risk_level` junto.

## Fiscal

`ci/validate_metadata.py::check_derived_from` (as três igualdades);
`ci/validate_metadata.py::check_pending_judgment` (sentinela fora de documento promovido);
`ci/audit_governance.py::check_ingest_pipeline` (agente e fiscal resolvíveis, ordem sem duplicata,
nenhuma escrita no alvo); `harness/schemas/ingest-pipeline.schema.json`;
`harness/policies/ingestao.md`; `.github/workflows/governance.yml`.
