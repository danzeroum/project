---
description: Transforma o alvo materializado em metadado governável, fase a fase, com proveniência.
---

# /ingerir

Você está num **derivado** já ancorado e bootstrapado. Sua tarefa é executar
`harness/pipeline/ingest.yaml`, fase a fase, **parando em cada `gate: human_approval`**.

**Pare antes de começar se** `project.yaml:project.kind` não for `derived`, ou se
`workspace/target/` não existir. No segundo caso a resposta é `/bootstrap`, não improvisar.

## As três regras que você não negocia

1. **O alvo é lido, nunca escrito.** Nenhum branch, commit, issue ou PR lá. Se um achado precisa
   chegar ao alvo, ele vira entrada no backlog daqui — o canal de retorno é decisão declarada em
   `harness/harness.yaml`, não iniciativa sua.
2. **Todo item carrega `derived_from`** `{repo, sha, path, section}`, com `sha` **idêntico** ao de
   `target.lock`. Um item sem proveniência é uma afirmação sobre o alvo que ninguém consegue
   reconferir.
3. **Você não julga.** `risk_level`, `likelihood`, `impact`, base legal e finalidade saem como
   `pending_judgment`, e o documento sai `source_of_truth: false` com `generated_from` preenchido.
   Promover é a fase `ING-07`, e ela tem gate humano.

## Como rodar

```bash
python ci/inventory_code.py     # ING-01: o que existe no alvo
```

Depois siga as fases na ordem de `harness/pipeline/ingest.yaml`. Cada fase declara seus `inputs`,
`outputs`, o agente responsável (contrato em `harness/agents/<nome>/`) e o fiscal que a confere.

Tudo vai por **change-proposal** — uma por fase, ou uma por bloco coeso de fases sem gate. O
`required_gates` inclui `inventory` e `metadata-validation`.

## Onde a ingestão costuma errar

- **Fronteira de componente.** Agrupar arquivos é julgamento de domínio, não dedução. Erre para o
  lado de componentes menores: fundir depois é um diff; separar depois desfaz rastreabilidade já
  declarada.
- **Capacidade inventada.** Se o alvo não documenta a intenção de um módulo, não invente uma:
  proponha o componente e deixe a capacidade para o julgamento humano. `status: proposed` existe
  para isso.
- **Proveniência genérica.** `path` apontando para o diretório em vez do arquivo torna
  `/sincronizar` incapaz de dizer que aquele item ficou velho.

## Pronto quando

- [ ] `python ci/validate_all.py` sai `0`
- [ ] nenhum `pending_judgment` sobrou em documento `source_of_truth: true`
- [ ] todo `derived_from.sha` casa `target.lock`
- [ ] nenhum arquivo sob `target.code_roots` está órfão
- [ ] o alvo não recebeu nenhuma escrita
