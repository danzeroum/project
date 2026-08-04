# CLAUDE.md — doutrina operacional deste repositório

> **Acabou de clonar?** A porta de entrada é `BOOTSTRAP.md`, e ela começa por uma pergunta:
> este repositório é **molde** ou **derivado**? Leia `project.yaml:project.kind` — não presuma.
> `python ci/adoption_status.py` responde e diz o próximo passo.

Duas frases explicam quase todas as decisões daqui:

> **O projeto declara configuração e autorização; o padrão fornece o motor e as verificações.**
>
> **Uma trava que o vigiado pode desligar em silêncio não é uma trava.**

## Antes de encerrar qualquer tarefa

```bash
python ci/validate_all.py
```

É exatamente o que `.github/workflows/governance.yml` roda. Falhou aqui, falha lá. O hook `Stop`
executa isso automaticamente, mas não conte com ele: o hook é ergonomia, o CI é o gate.

Códigos: `0` conforme · `1` divergência entre o declarado e o real · `2` algum fiscal não
conseguiu fiscalizar (YAML ilegível, laudo fora do próprio schema, `src/` que não parseia).

## As três fronteiras de confiança

| Camada | Onde vive | Dona da verdade |
|---|---|---|
| **Padrão — WebQA Suite** | repositório externo, versionado | julgamento de segurança |
| **Projeto consumidor** | este repositório | autorização + configuração, só declarativo |
| **Harness** | `harness/` | orquestração: qual modo roda, quem dispara, onde fica a evidência |

## Proibições duras

- **Não criar `webqa/`, `checks/` nem `data/caminhos-sensiveis.yaml`.** Uma cópia local da lista
  curada pode ter uma linha removida, e o laudo passa a dizer "nenhum achado" sem erro nem aviso.
- **Não restatar a versão do padrão** fora de `requirements-qa.txt`. Cópias derivam e a comparação
  entre projetos passa a mentir. O único espelho tolerado é `tests/qa/config.yaml`, sob igualdade
  verificada.
- **Não editar `docs/metadata-graph.md` à mão** — é derivado. Regerar: `python ci/generate_graph.py`.
- **Não exportar `WEBQA_*`.** Os gates da suíte são fail-closed por variável de ambiente; um
  agente que consegue defini-las se autoriza a sondar.
- **Não escrever enforcement em markdown.** Regra que precisa morder ganha schema, passo de CI ou
  gate — nunca um parágrafo.
- **Não afrouxar um fiscal para fazer o CI passar.** Se um fiscal acusa, ou o repositório está
  errado, ou a decisão precisa ser mudada explicitamente. Editar o fiscal é a terceira opção, e é
  a errada.

## Caminhos protegidos

`.github/`, `harness/`, `ci/`, `governance/`, `CLAUDE.md`, `.claude/`,
`tests/qa/escopo-autorizado.yaml`, `requirements-qa.txt`.

Mudança nesses caminhos começa por uma **change-proposal** declarada em
`harness/change-proposals/` (ADR-004), validada antes de executada. Risco `high`/`critical` exige
aval humano por trava de schema — um agente não se auto-aprova mudança de alto risco. O fiscal
real é CODEOWNERS + branch protection; o hook `PostToolUse` só evita descobrir isso no CI.

## Regra do metadado novo

Todo YAML de metadado novo custa quatro coisas, e é deliberado:

1. schema em `harness/schemas/`;
2. entrada em `DOCS` de `ci/validate_metadata.py`;
3. etapa em `harness/stages.yaml` (senão a partição do repositório não fecha);
4. política em `harness/policies/` terminando em `Fiscalizado por:` resolvível.

## Regra do ADR novo

Um ADR `accepted` **sem asserção executável é recusado pelo schema**. Declare ao menos uma em
`architecture/adr/index.yaml`: `path_absent`, `path_present`, `import_required`,
`import_forbidden`, `file_matches`, `file_lacks`, `schema_lock` — ou `manual`, com justificativa,
quando o que a decisão promete genuinamente não for verificável por máquina.

Asserção cujo alvo não existe **não passa**: vira `assertion_unresolvable`. Uma trava que não
encontra o que vigiar está quebrada, não satisfeita.

## Regra do campo novo (LGPD)

Qualquer campo com forma de dado pessoal exige, no mesmo PR:

1. entrada em `governance/data-inventory.yaml` — finalidade, base legal, retenção, `CMP-*` dono;
2. rodar a skill **`/revisao-lgpd`** (contrato do agente em `harness/agents/privacy/`);
3. atualizar `governance/ripd.md` e `governance/privacy-review.yaml`;
4. recalcular o escopo: `python ci/audit_lgpd.py --print-fingerprint`.

O primeiro campo inventariado muda o tipo de julgamento exigido (Parecer → RIPD completo), passa
a exigir encarregado (Art. 41) e os quatro endpoints de direitos do titular (Art. 18). Três travas
disparam juntas.

Nunca suprima um achado apagando termo do léxico de `ci/audit_lgpd.py`. Suprimir é **declarar**
em `data-inventory.yaml:scan.exclusions`, com justificativa e sob revisão.

## Etapas do projeto

`harness/stages.yaml` enumera as treze etapas com seus artefatos e fiscais. Todo arquivo do
repositório pertence a exatamente uma etapa ou a uma isenção declarada — diretório novo exige
declarar a que etapa pertence. É o que faz "validar todas as etapas" ser invariante em vez de
promessa.

## Regra do papel do repositório

`project.yaml:project.kind` é `mold` ou `derived`, e o schema trata os dois como papéis
estruturalmente distintos: **derivado exige o bloco `target`; molde o proíbe.** Um molde ancorado
num alvo específico deixou de ser genérico, e a genericidade é o produto.

O SHA do alvo mora **só** em `target.lock` — mesma regra da versão da régua, mesma razão. E
**nenhum alvo é especial**: nome, stack, caminho ou URL de alvo em `ci/` ou `harness/` reprova por
`ADR-008-A5`. Tudo que é do alvo mora em `project.yaml:target`, `target.lock` e `workspace/`.

## Onde ler mais

`BOOTSTRAP.md` (porta de entrada), `README.md` (arquitetura),
`docs/PLANO-MOLDE-VIVO.md` (para onde isto está indo), `docs/COMO-ADOTAR.md` (playbook de adoção),
`WEBQA_CONSUMER_CONTRACT.md` (interface com a suíte), `harness/policies/` (índice das regras e
seus fiscais), `architecture/adr/` (as decisões e suas asserções).
