# Política: toda mudança proposta é declarada antes de executada

Uma mudança — especialmente proposta por agente — declara, num artefato versionado, o que afeta, o
risco, os gates exigidos e se precisa de aval humano. É o que a harness lê para **rotear, bloquear ou
escalar** (ver `decision_policy` em `harness/harness.yaml`).

Regras:
- **Risco `high`/`critical` exige `human_approval_required: true`** — trava estrutural no schema, não
  convenção. Um agente não pode se auto-aprovar uma mudança de alto risco.
- `change_mode` é sempre `pull_request`: a mudança passa por revisão, nunca é aplicada direto.
- A proposta é conferida na **forma** — schema, cabeçalho, padrão dos IDs — e **nunca** contra o
  metadado de hoje.

## Por que os IDs não são resolvidos contra o presente (CP-018)

Uma change-proposal fala do dia em que foi escrita; o metadado fala de agora. Resolver
`capabilities_affected`, `components_affected` e `risks` contra o presente faz as duas divergirem
por construção — e divergirem **exatamente quando a proposta funciona**. Medido: executar a
proposta que remove o negócio de exemplo invalida todas as propostas que o citavam, inclusive ela
mesma. Uma proposta que reprova por ter sido cumprida não é um registro com defeito; é o fiscal
fazendo a pergunta errada.

**Registro é imutável.** A correção mora no fiscal, jamais na história: editar uma proposta
executada para "consertar" um ID reescreveria o que foi decidido, que é a única coisa que o
artefato existe para preservar.

## A troca de guarda

O que este fiscal pegava era um ID **digitado errado** no momento da escrita. Isso passa a ser
pego pela **revisão humana do pull request** — a única camada que distingue "ID errado" de "ID que
existia quando isto foi escrito". A trava não sumiu por descuido: mudou de lugar, e está escrito
aqui para que a ausência não seja lida como esquecimento e reintroduzida.

A isenção **acaba na change-proposal**. Metadado vivo — capacidades, componentes, ADRs,
threat-model, backlog, superfícies — segue com resolução de ID cobrada, porque descreve o que **é**,
não o que foi decidido.

---

Fiscalizado por: `harness/schemas/change-proposal.schema.json` (forma + risco alto ⇒ aval, via
`if/then`, e o padrão dos IDs); `ci/validate_metadata.py::check_change_proposals` (schema e
invariantes de cabeçalho, sem resolver ID contra o presente); revisão humana do pull request
(ID digitado errado no momento da escrita).
Declarado em: `harness/change-proposals/` (contrato em `README.md`, exemplo em `EXAMPLE-CP-001.yaml`).
Falha como: proposta fora do schema, cabeçalho inválido ou risco alto sem aval ⇒ erro de CI.
