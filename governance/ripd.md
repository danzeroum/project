# Parecer de Proporcionalidade — proteção de dados

> **Tipo de julgamento:** Parecer de Proporcionalidade (não RIPD completo).
> **Por quê:** o sistema não trata dados de titulares. O tratamento possível é **incidental e
> efêmero**, restrito a evidência de auditoria. Art. 38 da LGPD exige RIPD quando há tratamento
> que possa gerar risco às liberdades civis e aos direitos fundamentais dos titulares; aqui o
> registro proporcional é este parecer. O tipo exigido **não é escolha**: `ci/audit_lgpd.py`
> deriva-o de `governance/data-inventory.yaml` e reprova se o registrado não corresponder.
>
> Produzido pela skill `/revisao-lgpd`. O registro tipado — fingerprint, issues, escopo não
> avaliado — está em `governance/privacy-review.yaml`; este arquivo é a prosa.

## 1. Papel do sistema

Carcaça de projeto consumidor com uma harness declarativa de governança. O negócio de exemplo
(`src/project/pricing.py`, `src/project/ports.py`) opera sobre `sku`, `quantidade` e
`preco_centavos` — nenhum dado de pessoa natural. A harness orquestra o consumo da WebQA Suite
como padrão externo; ela não persiste cadastro, não expõe endpoint público
(`classification.internet_exposed: false`) e não possui banco de dados.

**Papel LGPD:** nenhum (`controller.role: none`). Não é controlador nem operador de dados de
titulares. Onde há dado pessoal, ele é de colaborador do próprio projeto, não de titular-cliente.

**Escopo desta revisão:** todo o repositório — metadados de negócio, arquitetura, design,
governança, código de `src/`, testes, configuração declarativa de QA e workflows de CI. O que
não foi avaliado está listado em `privacy-review.yaml:not_assessed`.

## 2. Dados incidentais capturados

| Vetor | Dado possível | Natureza |
|---|---|---|
| `harness/runs/` | corpo de resposta do alvo auditado em modo `passive` — pode conter dado pessoal do sistema auditado | incidental, efêmero |
| Artifacts do CI (`harness/reports/`) | laudos derivados da evidência acima | incidental, efêmero |
| `project.yaml:business.stakeholders` | identificação dos responsáveis pelo projeto | dado pessoal de colaborador |
| `tests/qa/escopo-autorizado.yaml` | `proof_of_possession.reference` pode nomear quem autorizou | dado pessoal de colaborador |
| Metadados de commit | nome e e-mail do autor | inerente ao Git, fora do controle da aplicação |

Nenhum desses é dado sensível (Art. 5º, II). Nenhum é coletado de titular-cliente. A varredura
determinística de `ci/audit_lgpd.py` sobre a superfície declarada em `harness/stages.yaml`
retorna zero identificadores com forma de dado pessoal no código e nos metadados.

## 3. Controles proporcionais

Aplicados na hierarquia **não coletar > mascarar na escrita > reter pouco > criptografar** —
criptografia é segunda linha para dado já minimizado, não a primeira resposta.

1. **Não coletar (primeira linha, e mora fora deste repositório).** A sanitização dos achados é
   responsabilidade da WebQA Suite, e o contrato de consumo já a declara: os achados chegam
   sanitizados (`harness/schemas/report.schema.json`). Este projeto não pode afrouxar essa
   régua, porque não a possui — é a consequência prática do ADR-001.
2. **Não coletar (segunda linha, local).** Os modos que geram tráfego contra um alvo real
   (`load`, `active_discovery`) são `human_only` e vivem em job segregado com aprovação
   (`harness/harness.yaml`, `.github/workflows/qa.yml`). Agente nenhum dispara sondagem.
3. **Reter pouco.** `evidence_retention_days: 90` em `project.yaml` e `retention_days: 90` em
   `tests/qa/campanha.yaml`. A igualdade entre os dois é fiscalizada — divergência silenciosa
   entre duas declarações de retenção seria uma mentira de retenção.
4. **Não versionar.** `harness/runs/`, `harness/reports/` e `harness/state/` são gitignored: a
   evidência não entra no histórico do Git, de onde não se apaga.
5. **Minimizar identificação de colaborador.** `business.stakeholders` usa identificador de
   conta (handle) em vez de nome civil e e-mail pessoal. Um handle já satisfaz a finalidade
   (saber a quem escalar), e coletar menos é sempre a primeira opção.
6. **Registro das operações sempre em dia.** `governance/data-inventory.yaml` é fiscalizado a
   cada push; um campo com forma de dado pessoal fora dele reprova o CI (Art. 37).

## 4. Controles descartados, com justificativa

- **Criptografia em repouso de `harness/runs/`** — desproporcional. A evidência já chega
  sanitizada pelo padrão externo, é efêmera (90 dias), não versionada e não contém dado de
  titular-cliente. Introduzir KMS e rotação de chave numa carcaça de projeto adicionaria
  superfície de gestão de segredo sem reduzir risco real. Reavaliar se o inventário deixar de
  ser vazio ou se o modo `passive` passar a apontar para alvo de produção com dado pessoal.
- **Endpoints de direitos do titular (Art. 18)** — não aplicável. Não há titular: o sistema não
  mantém base de dados pessoais. O schema do inventário permite `null` nos quatro direitos
  **enquanto** `fields` estiver vazio, e passa a cobrá-los no primeiro campo inventariado.
- **RIPD completo (8 seções)** — desproporcional agora, e o próprio fiscal recusaria: com
  `controller.role: none` o tipo exigido é este parecer. Vira obrigatório automaticamente
  quando o papel mudar.
- **Anonimização/pseudonimização de metadado de commit** — fora do alcance da aplicação e
  contrário à rastreabilidade de autoria que a governança do repositório exige (Art. 7º, IX,
  com finalidade legítima e expectativa clara de quem contribui).

## 5. Riscos residuais

| Risco | Severidade | Tratamento |
|---|---|---|
| Auditoria `passive` contra alvo de produção capturar dado pessoal de terceiro em `harness/runs/` | Médio | Sanitização no padrão externo + retenção de 90 dias + evidência não versionada. Reabrir este parecer se o alvo declarado em `tests/qa/config.yaml` deixar de ser ambiente de teste — a mudança daquele arquivo altera o `scope_fingerprint` e força a reavaliação. |
| Consumidor da carcaça adicionar PII sem inventariar | Médio | `RISK-PRIV-001`, fiscalizado por `ci/audit_lgpd.py` (varredura de tratamento-sombra) a cada push. |
| Este parecer envelhecer em relação ao sistema | Médio | `RISK-PRIV-002`: `scope_fingerprint` em `privacy-review.yaml` é conferido a cada push; divergiu, o CI reprova. |

## 6. Aprovação

- Encarregado (DPO): _não indicado — dispensado enquanto `controller.role` for `none` (Art. 41)_
- Revisor de Engenharia: ______________________  Data: ____/____/________

> Este parecer cobre o estado do repositório identificado pelo `scope_fingerprint` registrado em
> `governance/privacy-review.yaml`. Mudou o escopo, o parecer deixa de falar deste sistema e
> `ci/audit_lgpd.py` reprova até que ele seja refeito.
