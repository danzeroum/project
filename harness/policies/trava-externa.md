# Política: a trava que o vigiado não desliga

> Uma trava que o vigiado pode desligar em silêncio não é uma trava.

Esta política existe porque a frase acima era **parcialmente falsa** aqui: `harness.yaml` declarava
que o fiscal real de `protected_paths` é CODEOWNERS mais branch protection, e nenhum fiscal
conferia que a proteção estava ligada.

## Camada local — entregue

`ci/verify_protection.py` consulta a API e reprova se a `main` não exige review de **code owner**,
se permite force push, ou se algum `protected_path` não tem dono em CODEOWNERS.

Sem credencial: `protection_unverifiable` (exit 3). Indeterminação auditável, nunca verde.

Um detalhe da API impõe honestidade: `GET /branches/{b}/protection` responde **404 tanto para "sem
proteção" quanto para "sem permissão de ver"**. Indistinguíveis de fora — então o verificador
devolve indeterminação em vez de escolher a conclusão mais grave. Escolher a mais grave produziria
alarme de fraude toda vez que o token não tivesse escopo.

## Segundo eixo: a âncora das releases

`--tags` faz a mesma pergunta sobre outro namespace de ref: **a tag de uma release é imóvel?**

O ADR-025 deixa o workflow de release **criar** a ref depois de validar, e conta com o servidor
para não deixá-lo **movê-la**. O `git push` sem `--force` recusa atualizar tag existente — mas essa
recusa é do **cliente**: quem tem token e vontade empurra com `--force`. O que transforma a recusa
em trava é o ruleset, e por isso as regras exigidas são exatamente as que impedem mover e apagar:

| Regra exigida | O que ela impede |
|---|---|
| `deletion` | a tag sumir |
| `non_fast_forward` | a tag ser reescrita por force push |
| `update` | a tag ser reapontada |

`creation` **não** é exigida, de propósito: exigi-la trancaria o único caminho legítimo de
publicação. Uma trava que impede o trabalho legítimo é desligada por quem tem trabalho a fazer.

Bypass list não-vazia também reprova — quem pode bypassar pode mover a tag, e a trava passaria a
valer só para quem não precisaria dela.

Enquanto `external_audit.enabled` for `false`, este eixo **reporta e não bloqueia**, pela mesma
razão do eixo de branch. Ligar a flag torna as mesmas linhas bloqueantes sem mudar uma linha de
código.

## Camada externa — o que falta

**A camada local não equivale à externa.** Ela mora no mesmo repositório que fiscaliza: um PR com
privilégio suficiente remove o passo e a asserção que o vigia **no mesmo commit**, e o CI fica
verde porque a trava saiu junto com quem reclamaria dela.

Só quebra a circularidade um check com identidade emissora identificável, cuja obrigatoriedade
esteja em ruleset administrado **fora** daqui — imodificável por workflow, por `GITHUB_TOKEN` ou
por PR deste repositório. Sem essa raiz, a autoridade externa é decorativa: quem muda o workflow
muda a exigência junto.

## O desligado é declarado

`harness.yaml:external_audit.enabled: false`, com justificativa e um `accepted_risk` que precisa
**existir e ter data**. `check_external_attestation` reprova se o risco citado não existir ou não
tiver `due`: desligar a camada externa tem que custar um risco datado a alguém.

O achado de "desligada" é `info` e aparece a cada execução. Bloquear inverteria a decisão — a
ausência é risco **aceito com data** (`RISK-EXT-001`, `due: 2026-11-03`), não divergência a
corrigir hoje. Repositório vermelho por condição que ninguém aqui satisfaz é repositório cujo
fiscal se aprende a ignorar.

Ligada, o atestado passa a ser exigido: ausente, expirado ou de emissor não declarado **bloqueia**.

Fiscalizado por: `ci/verify_protection.py::verify_protection`, `ci/verify_protection.py::verify_tag_protection`, `ci/audit_governance.py::check_external_attestation`, `harness/schemas/protection-attestation.schema.json`
Declarado em: `harness/harness.yaml` → `external_audit`; `harness/change-proposals/CP-024-trava-externa-em-duas-camadas.yaml` (status `deferred`)
Falha como: proteção desligada ou caminho sem dono ⇒ exit 1; sem credencial ⇒ exit 3; risco aceito sem data ⇒ achado bloqueante.
