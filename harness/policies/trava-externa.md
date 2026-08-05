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

Este eixo **bloqueia** desde 05/08/2026, quando `external_audit.enabled` passou a `true` (CP-036).
A CP-031 já o escrevera assim: a flag decide se as lacunas reportam ou bloqueiam, e ligá-la exerceu
o desenho sem editar uma linha do fiscal.

## Camada externa — entregue (CP-036)

**A camada local não equivale à externa.** Ela mora no mesmo repositório que fiscaliza: um PR com
privilégio suficiente remove o passo e a asserção que o vigia **no mesmo commit**, e o CI fica
verde porque a trava saiu junto com quem reclamaria dela.

Quem quebra a circularidade é `danzeroum/harness-authority`:

| Peça | Por que conta como externa |
|---|---|
| repositório próprio | nenhum workflow, token ou PR **deste** lado o edita |
| GitHub App próprio | identidade emissora que não é o `GITHUB_TOKEN` daqui |
| cron diário, atestado de 25h | execução perdida faz o carimbo **expirar**, não persistir |
| lê rulesets de `main` e `refs/tags/v*` | a configuração real do servidor, de fora |

A autoridade **propõe** por PR e não escreve na `main`: um verificador com direito de push poderia
reescrever a evidência das auditorias anteriores.

### Quem assina, e por que isso vem junto

Ligar sem conferir o emissor produziria *"alguém atestou"*, não *"quem devia atestou"* — e um molde
que exige atestado e aceita qualquer um é **pior** que um molde com a camada desligada. Desligada,
a lacuna está escrita e datada; ligada-sem-emissor, ela fica escondida atrás de um JSON que quem
tem direito de merge escreve à mão em trinta segundos.

`external_audit.authorized_issuer` declara identidade e tipo, e o schema torna a combinação
perigosa **inexpressável**: `enabled: true` exige o bloco.

### Três estados, três achados (princípio (h))

| Achado | O que aconteceu | Para onde olhar |
|---|---|---|
| `EXT-AUDIT-SEM-ATESTADO` | o verificador não entregou | o cron da autoridade, ou a credencial dele |
| `EXT-AUDIT-ATESTADO-EXPIRADO` | ele entregou, e envelheceu | quantas execuções foram perdidas |
| `EXT-AUDIT-EMISSOR-NAO-AUTORIZADO` | **alguém escreveu isso à mão** | o histórico do arquivo |

Não se excluem: a checagem de emissor não tem `return`, então expirado **e** de emissor errado
produz os dois — são dois problemas, e consertar um não conserta o outro.

## O PR diário mergeia sozinho — e só ele (CP-037 / ADR-029)

O carimbo vale 25h e o cron abre um PR por dia. Exigir um clique humano nele daria à trava um
gargalo **diário**, e atrito diário é como trava boa vira trava contornada (princípio (e)).

`.github/workflows/atestado-automerge.yml` habilita o **auto-merge nativo** do GitHub sob três
condições:

| # | Condição | Quem confere |
|---|---|---|
| 1 | o diff contém **exclusivamente** o `attestation_path` | `ci/automerge_gate.py::decidir` |
| 2 | o autor é o App declarado em `authorized_issuer` | `ci/automerge_gate.py::decidir` |
| 3 | todos os checks obrigatórios passam | o auto-merge nativo |

A terceira não é conferida por código daqui, de propósito: um passo que lesse o estado dos checks
leria um estado que ainda vai mudar. `--auto` entrega a pergunta a quem tem a resposta.

O gatilho é `pull_request_target` — o workflow vem da **base**, e nenhum passo faz checkout do head
nem executa uma linha vinda dele. Com `pull_request`, um PR que alterasse o workflow escreveria as
próprias checagens que decidem se ele pode auto-mergear.

**Recusar não é reprovar:** um PR humano que toca o atestado é legítimo, só não é auto-mergeável —
o portão sai `0` e diz por quê no resumo do job. Quem sai diferente de `0` é a indeterminação
(`exit 2`), porque um portão que não sabe contra o que comparar não libera nada.

## O desligado continua declarável

`enabled: false` segue sendo um estado legítimo, com justificativa e um `accepted_risk` que precisa
**existir e ter data**. `check_external_attestation` reprova se o risco citado não existir ou não
tiver `due`: desligar a camada externa tem que custar um risco datado a alguém. O achado de
"desligada" é `info` e aparece a cada execução — bloquear inverteria a decisão, e vermelho
permanente é como um fiscal se aprende a ignorar (ADR-019).

## O que ainda falta, e não é código

Dois passos de admin no GitHub, ambos fora do alcance de qualquer PR deste repositório:

1. tornar o check da autoridade **obrigatório no ruleset da `main`** — é o que separa *"o CI
   reprova"* de *"o merge é impossível"*;
2. habilitar o **auto-merge nativo** (Settings → General → Pull Requests → *Allow auto-merge*).
   Sondado em 05/08/2026: está **desmarcado**. Enquanto estiver, o PR diário permanece manual e o
   passo emite um `::warning::` com essa instrução — **sem** reprovar o job, porque capacidade que
   falta no ambiente não é defeito do PR, e vermelho permanente é como um fiscal se torna ignorado.

Por isso `RISK-EXT-001` está `mitigated` e não `closed`: fechar enquanto esses passos não existem
seria carimbar a parte que falta.

Fiscalizado por: `ci/verify_protection.py::verify_protection`, `ci/verify_protection.py::verify_tag_protection`, `ci/audit_governance.py::check_external_attestation`, `ci/automerge_gate.py::decidir`, `harness/schemas/protection-attestation.schema.json`
Declarado em: `harness/harness.yaml` → `external_audit`; `harness/change-proposals/CP-024-trava-externa-em-duas-camadas.yaml` (status `deferred`); `harness/change-proposals/CP-036-ligar-a-autoridade-externa.yaml`; `harness/change-proposals/CP-037-auto-merge-do-atestado.yaml`
Falha como: proteção desligada ou caminho sem dono ⇒ exit 1; sem credencial ⇒ exit 3; atestado ausente, expirado, fora do schema ou de emissor não autorizado ⇒ achado bloqueante; portão do auto-merge sem declaração contra a qual comparar ⇒ exit 2 (nunca liberação).
