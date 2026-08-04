# ADR-013 — Segurança é departamento com artefato e fiscal, não um campo `security_owner`

- **Status:** accepted
- **Data:** 2026-08-04
- **Riscos relacionados:** RISK-SEC-001, RISK-DEP-001

## Contexto

Doze ADRs depois, este repositório governa arquitetura, negócio, design e governança como camadas
de verdade: cada uma tem schema, fiscal, etapa e política. Segurança tinha um campo —
`project.yaml:business.stakeholders.security_owner` — e alguns riscos que falavam da própria
harness.

Um dono sem artefato é um dono sem trabalho verificável. Não havia onde escrever "este componente
pode ser adulterado por aqui", nem como perguntar "quais ameaças de elevação de privilégio existem
neste sistema?". E não havia nada que impedisse uma dependência nova de entrar sem que ninguém
registrasse por que ela existe e quem a mantém — a régua estava pinada, mas o pin cobre uma
dependência de um universo inteiro.

É a mesma família de silêncio que a Fase E descobriu, e pela mesma razão: ausência não reprova, a
menos que alguém escreva a trava que pergunta pelo que falta.

## Decisão

**1. `security/` como departamento.** Dois artefatos, dois schemas, uma etapa (`STAGE-SECURITY`),
uma política, dois fiscais. O mesmo custo de qualquer metadado novo, pago de propósito.

**2. Ameaça sem mitigação não existe.** `mitigations` tem `minItems: 1`, com referências tipadas
— a mesma forma dos `controls[]` do risk-register, porque é a mesma pergunta ("o que segura
isto?") sobre outro objeto.

**3. Ameaça sem residual rastreável não existe.** `residual_risk` aponta para um `RISK-*` real.
É o que impede a segurança de virar ilha: com o residual ancorado, a ameaça herda dono, prazo e a
cobertura reversa da Fase E. Sem ele, o modelo de ameaças seria um arquivo que só o autor lê.

**4. STRIDE fechado.** Categoria livre aceita `outros` para sempre, e ninguém consegue perguntar
"quais ameaças de elevação de privilégio existem?". É a mesma razão pela qual `classification`
usa enums.

**5. Dependência declarada é dependência inventariada, nos dois sentidos.** Declarada e não
inventariada é achado; inventariada e não declarada também — entrada morta faz o inventário
parecer mais completo do que é.

**6. O inventário lê declaração, não ambiente.** Sem `tomllib`, sem consultar `site-packages`: um
inventário conferido contra o que está instalado passaria ou reprovaria conforme o computador de
quem roda, que é o oposto de fiscalizável.

**7. `pin_kind` descreve o que é.** O fiscal não exige `exact` em tudo — exige que a escolha
esteja escrita. `range` declarado é decisão auditável; `range` escondido é dependência que muda
sozinha entre dois runs.

## Consequências

- Acrescentar biblioteca passa a exigir uma entrada no inventário, com dono e razão. É o efeito
  pretendido, não um efeito colateral.
- O molde ganha três ameaças reais, e uma delas (`THREAT-PRICING-INFO`) carrega uma mitigação
  `accepted` declarando que **não há runtime aqui** e que o derivado herda a ameaça. Registrar a
  herança é o oposto de fingir cobertura.
- `severity` aceita `pending_judgment`: nenhuma ferramenta decide gravidade de ameaça, e o
  sentinela é recusado em documento promovido pela trava da Fase D.
- Custo assumido: nenhum fiscal descobre a ameaça que ninguém pensou. O modelo de ameaças é
  escrito por gente, e o que a máquina garante é que a ameaça pensada não fica sem tratamento,
  sem residual e sem dono. Fingir o contrário — um scanner que "gera" o modelo — produziria
  julgamento de máquina com aparência de análise humana.

## Fiscal

`ci/validate_metadata.py::check_threat_model`; `ci/validate_metadata.py::check_dependency_inventory`;
`harness/schemas/threat-model.schema.json` (mitigação `minItems: 1`, `residual_risk` obrigatório,
STRIDE fechado); `harness/schemas/dependencies.schema.json`; `harness/policies/seguranca.md`;
`.github/workflows/governance.yml`.
