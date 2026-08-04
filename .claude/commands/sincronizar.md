---
description: Compara o derivado com o alvo que continuou evoluindo e transforma o drift em trabalho declarado.
---

# /sincronizar

O alvo continua evoluindo; `target.lock` não. Sua tarefa é medir a distância, transformá-la em
**trabalho concreto** e — só depois de aprovado — avançar o lock.

**Pare antes de começar se** `project.yaml:project.kind` não for `derived`. Um molde não governa
alvo algum, e não há o que sincronizar.

## A regra que você não negocia

**O lock não avança aqui.** Avançá-lo é decisão declarada em change-proposal, porque decidir se um
metadado ainda vale é julgamento, não diff. Um `/sincronizar` que atualizasse o lock sozinho
trocaria um drift **visível** por um metadado **errado** — que é estritamente pior, porque some.

## Passos

### 1. Medir

```bash
python ci/bootstrap.py --check-drift
```

`em-dia` encerra o comando. `atrasado` traz o SHA remoto; `indisponivel` significa que o alvo saiu
do escopo da sessão (`add_repo`) ou o commit sumiu por force-push — diga qual e pare.

### 2. Traduzir em trabalho

```bash
python ci/audit_conformance.py --sync-diff <sha-remoto>
```

A resposta útil não é *"o alvo andou 40 commits"* — é *"estes seis itens descrevem arquivos que
mudaram"*. Cada item da lista é um metadado cujo `derived_from.path` aponta para arquivo alterado
entre o lock e o remoto: ele **pode** ter ficado velho, e alguém precisa olhar.

Arquivo novo sob `code_roots` não aparece nessa lista — ele aparece como **código órfão** quando o
workspace avançar. As duas metades juntas são o diff de ingestão completo.

### 3. Propor

Uma change-proposal (`risco: high` — ela reancora o repositório inteiro) declarando:

- o SHA de origem e o de destino;
- os metadados afetados, item a item, com o que muda em cada um;
- que a revisão de conformidade vai vencer, porque `conformance_fingerprint` inclui o lock.

### 4. Executar, depois de aprovada

1. atualizar `target.lock:target_sha`;
2. `python ci/bootstrap.py` — materializa o alvo no SHA novo;
3. reingerir o que a lista apontou (`/ingerir`, fases afetadas), atualizando `derived_from.sha`;
4. rodar o agente `conformance` e regravar `scope_fingerprint`;
5. `python ci/validate_all.py`.

O passo 4 não é burocracia: sem ele o repositório fica verde nos fiscais e com uma validação
semântica que fala de outro commit.

## Pronto quando

- [ ] `python ci/bootstrap.py --check-drift` diz `em-dia`
- [ ] `python ci/validate_all.py` sai `0`
- [ ] `python ci/audit_conformance.py` sai `0`
- [ ] nenhum `derived_from.sha` ficou para trás
- [ ] o alvo não recebeu nenhuma escrita
