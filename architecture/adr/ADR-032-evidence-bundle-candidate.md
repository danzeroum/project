# ADR-032 — Evidência de produtor PSE entra por matriz fechada, e a análise é fixture

**Status:** accepted · **Data:** 2026-08-17 · **Proposta:** CP-051
**Atualização (Sprint 6.2):** PR #2 da pse-suite mergeada em 17/08/2026 20:23:21 UTC — estado do
produtor movido de `candidate_not_merged` para `merged_unreleased`.

## Contexto

A pse-suite entregou um adapter piloto (`laudo-pse-1.0` → `evidence-bundle/v1 draft`) numa
branch candidata. A PR #2 foi **mergeada** — o adapter está no `main` da pse-suite (commit
`443da92dbdb22a9af18aa6eebb51aac2da901458`, source `f19e593257b8480e7822795ba49a36f284963371`) —
mas **sem release**: não há tag `v0.4.0`, manifesto de release nem pin versionado. E isso é
justamente o problema: o bundle mergeado tem schema, hash e assertions, tudo com a cara de
evidência oficial. Se o estado do produtor não estiver travado, alguém trata o bundle como
evidência de produção no dia em que ele aparecer num CI estrito — e o pior modo de falha é o de
sempre: **nada fica vermelho, porque nada quebrou**.

A alternativa "não falar do assunto até releasear" também falha: a modelagem, os testes e a
documentação de como consumir esses bundles ficariam bloqueados por uma decisão de release que não
é deste repositório — e o repositório pararia de avançar por causa de um estado que ele não
controla.

## Decisão

**Evidência de produtor não releaseado pode ser analisada em fixture/preparação — nunca em CI
estrito, nunca em produção, e não satisfaz controle algum.** Toda a fronteira vive numa matriz
declarada — `harness/suite-contract/evidence-bundle/compatibility-matrix.yaml` (o *assurance
lock*) — e o schema dela é fechado nos dois sentidos:

1. **O estado do produtor é um enum de três elementos, com consequências por estado.** O schema
   (`harness/schemas/evidence-reference.schema.json`) admite `candidate_not_merged`,
   `merged_unreleased` e `released`. Os dois primeiros têm `release_eligible: const false`; o
   terceiro só é expresso com o bloco `release` — tag, versão, commit, manifesto e hash de
   artefato verificáveis. **Merge no main ≠ release publicado ≠ dependência elegível para
   produção.** Nada fora destes três estados existe como opção de erro; `released` sem metadados
   é inexpressível, não proibido.

2. **A referência ganha `adapter_source_commit`.** O SHA que um bundle verificável carrega em
   `producer.suite_commit` é o do adapter emitido/mergeado — hoje `f19e5932…`. Source commit
   divergente é acusado (M39): um bundle que não saiu do adapter mergeado não é evidência do
   produtor declarado.

3. **O fecho de situações é completo por contagem.** A matriz tem exatamente 11 situações
   (`minItems`/`maxItems`): local-execution → `blocked` no CI estrito; candidato não mergeado →
   `blocked` em produção e `accepted_in_fixture_only` em fixture; **mergeado sem release →
   `blocked` em produção E como fonte no CI estrito**, `accepted_in_fixture_only` em fixture;
   `released` sem metadados → `blocked`; sem SHA → `blocked`; source commit divergente →
   `blocked`; `CTRL-DEP-001` → `not_satisfied`; release inexistente → `release_eligible: false`.
   Acrescentar uma décima segunda é edição de contrato — nova versão, novo ADR — nunca
   enriquecimento silencioso.

4. **A matriz é metadado novo, e paga as quatro coisas.** Schema
   (`assurance-lock.schema.json`), registro (entrada em `DOCS` de `ci/validate_metadata.py`),
   etapa (artefato em `harness/stages.yaml`) e política (`harness/policies/assurance-evidence.md`)
   — mais os testes de mordida que provam que a trava morde.

### O que a decisão deliberadamente NÃO faz

Não instala PSE, não executa `pse evidence-bundle` em CI, não abre rede, não cria
`requirements-pse.txt` ativo, não registra suite ativa em `harness/suites/`, não cria tag nem
release `v0.4.0` e não altera `CTRL-DEP-001` — que permanece `not_satisfied`. O produtor segue
apenas uma **referência**: `danzeroum/pse-suite`, main `443da92…`, source `f19e593…`, estado
`merged_unreleased`, `release_eligible: false`. A referência é de identificação (org/repo), nunca
uma URL — `ADR-008-A5` segue intocado, e o molde continua genérico.

### O que se recusou

- **Pular para `released`.** Sem tag `v0.4.0`, manifesto de release ou pin versionado, `released`
  seria uma promessa — e o schema faz o contrário: `released` exige os metadados. A mudança de
  estado (merge) aconteceu no mundo real e foi reconciliada; a de release ainda não aconteceu, e
  o schema não tem como mentir sobre ela.
- **Proibir a menção ao produtor.** `ADR-008-A5` proíbe URL de repositório em `harness/`; a
  referência é `org/repo`, o formato que o schema dela exige — e um `file_lacks` novo vela que
  nenhuma URL entre no diretório do contrato.
- **Criar uma suite ativa para a PSE.** Ficha com `status: active` em `harness/suites/` faria o
  runner genérico executar a régua no CI — o oposto da fronteira que esta decisão desenha. Sem
  release verificável, não há ficha.
- **Deixar o estado do produtor em prosa.** Um parágrafo que diz "ainda não releaseado" é a trava
  que se desliga por esquecimento. O enum de três estados é a trava que não existe como opção de
  erro.

## Consequências

O bundle mergeado pode ser modelado, referenciado e testado **hoje**, sem esperar release da PSE
e sem declarar falsamente que o produtor está publicado. A matriz é a autoridade de estado: mudou
o estado real do produtor (release), muda-se a matriz **e o enum do schema**, numa mudança de
contrato com ADR novo — nunca uma edição silenciosa.

O custo declarado: qualquer bundle que entre no repositório precisa de um fixture de três
variantes (estrito, local, sem SHA) com hashes canônicos conferidos, e qualquer situação nova é
mudança de contrato. É o preço de o "mergeado" não poder virar "releaseado" por engano.

## Fiscal

`ci/validate_metadata.py::main` (matriz validada contra o schema via `DOCS`); `ci/audit_governance.py`
(executa as asserções abaixo); `harness/schemas/assurance-lock.schema.json`;
`harness/schemas/evidence-reference.schema.json`; `harness/stages.yaml`;
`tests/governance/test_assurance_evidence_contract.py`; `tests/governance/test_candidate_adapter_reference.py`.