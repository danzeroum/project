# ADR-002 — Enforcement mora em schema, CI e gates, não em markdown

- **Status:** accepted
- **Data:** 2026-08-03
- **Riscos relacionados:** RISK-META-001

## Contexto

Documentos declarativos (políticas, metadados de negócio, contratos de agente) são fáceis de escrever
e fáceis de ignorar. Um arquivo de política em markdown depende de alguém ler e obedecer — é a placa de
"proibido fumar", não o detector ligado ao alarme. Metadado sem contrato verificável fornece contexto
opcional, não garantia.

## Decisão

Toda regra que precisa "morder" tem um fiscal executável:

- **Estrutural:** JSON Schema (forma, tipos, enums, padrões), validado no CI.
- **Semântico:** `ci/validate_metadata.py` (existência de path, resolução de IDs, coerência entre
  documentos), com a existência de código/teste condicionada à maturidade.
- **Operacional:** gates fail-closed da suíte e jobs segregados do CI.

`harness/policies/` é um **índice** que aponta para esses fiscais; uma entrada sem apontamento é
lembrete, nunca garantia.

## Consequências

- Divergência entre declaração e repositório vira falha visível de CI, não deriva silenciosa.
- Cada metadado novo custa um schema e um passo de validação — deliberadamente.
- A harness pode confiar no que os metadados declaram, porque o CI já os cruzou com a realidade.

## Fiscal

`ci/validate_metadata.py`, `.github/workflows/validate-metadata.yml`, `harness/schemas/*.json`.
