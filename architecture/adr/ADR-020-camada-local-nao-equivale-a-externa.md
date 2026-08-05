# ADR-020 — A camada local não equivale à externa

**Status:** accepted · **Data:** 2026-08-05 · **Proposta:** CP-024 (`deferred`)

## Contexto

O `CLAUDE.md` abre com a frase que rege este repositório:

> **Uma trava que o vigiado pode desligar em silêncio não é uma trava.**

Ela era parcialmente falsa aqui. `harness.yaml` declara que o fiscal real de `protected_paths` é
CODEOWNERS mais branch protection — e nenhum fiscal conferia que essa proteção estava ligada. A
declaração existia; a verificação, não.

## Decisão

**A verificação tem duas camadas, e a primeira sozinha não fecha a promessa.**

### Camada local (entregue)

`ci/verify_protection.py`, aplicada por um passo do `governance.yml`: consulta a API e reprova se a
`main` não exige review de code owner, se permite force push, ou se algum `protected_path` não é
coberto por CODEOWNERS. Sem credencial, emite `protection_unverifiable` (exit 3) — indeterminação
auditável, nunca verde por ausência de prova.

Um detalhe da API força honestidade: `GET /branches/{b}/protection` responde **404 tanto para "sem
proteção" quanto para "sem permissão de ver"**. Os dois casos são indistinguíveis do lado de fora,
então o verificador devolve indeterminação em vez de escolher a conclusão mais grave. Escolher a
mais grave produziria alarme de fraude toda vez que o token não tivesse escopo.

### Por que ela não basta

**Este passo mora no mesmo repositório que fiscaliza.** Um PR com privilégio suficiente remove o
passo e a asserção que o vigia **no mesmo commit** — e o CI fica verde, porque a trava saiu junto
com quem reclamaria dela. A circularidade é estrutural: nenhuma quantidade de código local a
resolve.

### Camada externa (o que completaria)

Um check com nome estável e **identidade emissora identificável**, cuja obrigatoriedade é
configurada em ruleset administrado **fora** do repositório fiscalizado — imodificável por
workflow, por `GITHUB_TOKEN` ou por PR daqui. Sem essa raiz administrativa independente, a
autoridade externa é decorativa: quem pode mudar o workflow muda a exigência junto, e o atestado
passa a certificar a si mesmo.

O atestado (`harness/schemas/protection-attestation.schema.json`) carrega `repository`, `branch`,
`checked_at`, `expires_at`, `ruleset_ref`, `issuer`, `verifier_version` e `config_digest`. Ausência,
expiração ou emissor não declarado bloqueiam.

## O estado desligado é declarado, não omitido

`harness.yaml:external_audit.enabled: false` com justificativa e um `accepted_risk` que **precisa
existir e ter data**. `check_external_attestation` reprova se o risco citado não existir ou não
tiver `due` — desligar a camada externa tem que custar um risco datado a alguém.

Com a flag desligada, o achado é `info` e aparece a cada execução. Bloquear seria inverter a
decisão: a ausência da autoridade externa é risco **aceito com data**, não divergência a corrigir
hoje. Um repositório vermelho por uma condição que ninguém aqui consegue satisfazer é um
repositório cujo fiscal se aprende a ignorar.

A alternativa — não escrever nada até a identidade existir — deixaria o repositório sem verificação
nenhuma por tempo indeterminado, e **sem lugar onde a lacuna aparecesse**. Com a flag, a lacuna é
barulhenta.

## Consequências

A CP-024 fica `deferred` e **não conta como implementada**. `RISK-EXT-001` registra a janela com
`due` em **2026-11-03**: ou a identidade externa foi viabilizada, ou o risco é re-aceito com data
nova (princípio (g) — risco aceito sem data é risco esquecido).

Ligar a camada externa passa a ser trocar uma flag e apontar o emissor. O código já está aqui.

## Fiscal

`ci/verify_protection.py::verify_protection` (núcleo puro) aplicado pelo `governance.yml`;
`ci/audit_governance.py::check_external_attestation` para o estado declarado e a validade do
atestado. As asserções `ADR-020-A*` provam que as duas peças continuam existindo e que o elo
risco-datado continua obrigatório.
