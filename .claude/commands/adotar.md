---
description: Deriva o gêmeo de governança de um repositório-alvo qualquer e o ancora por SHA.
argument-hint: <url-ou-owner/repo-do-alvo>
---

# /adotar — nascer o gêmeo de governança de `$1`

Você está num repositório **molde** (`project.yaml:project.kind: mold`). Sua tarefa é derivar dele
o gêmeo de governança do alvo `$1`, ancorá-lo e deixá-lo validando.

**Pare antes de começar se** `project.kind` não for `mold`: derivar a partir de um derivado
produziria um neto que ninguém governa. Diga o que encontrou e pare.

## Invariante que você nunca viola

**Nenhum alvo é especial.** Nada específico de `$1` — nome, stack, gerenciador de pacotes ou
caminho — pode acabar em `ci/` ou `harness/`. A asserção ADR-008-A5 reprova o CI se acabar. Tudo
que é do alvo mora em `project.yaml:target`, em `target.lock` e no `workspace/` efêmero.

E o alvo é **lido, nunca escrito**. Nenhum passo daqui cria branch, commit, issue ou PR no alvo.

## Passos

### 1. Trazer o alvo para o escopo

O escopo de GitHub desta sessão é limitado. Use `add_repo` com `owner` e `repo` de `$1` e
`access: "read"` — adotar é ler. Se a ferramenta recusar por autorização, **pare** e repasse o
motivo exato que ela deu, incluindo o caminho de liberação que ela indicar. Não tente contornar,
não adivinhe se o repositório existe, não relate como inacessível sem ter chamado a ferramenta.

### 2. Reconhecer o alvo — descobrir, nunca presumir

Clone raso e responda, com evidência de arquivo real:

| O que | Como | Vira |
|---|---|---|
| branch padrão | o que o remoto aponta — **não presuma `main`** | `target.ref` |
| SHA do HEAD dessa branch | `git rev-parse` | `target.lock:target_sha` |
| linguagens presentes | extensões dominantes sob os diretórios de código | `target.languages` |
| raízes de código | onde o código de fato mora (`src/`, `app/`, `packages/`, `lib/`, a raiz…) | `target.code_roots` |
| onde ficam os testes | convenção observada no alvo | insumo do inventário |

Monorepo, poliglota, sem testes e sem `src/` são todos casos válidos. Se você não conseguir
identificar nenhuma raiz de código, **pare e diga isso** — um `code_roots` chutado torna a
invariante do código órfão verdadeira por vacuidade, que é pior que ausente.

Apresente o reconhecimento e confirme com a pessoa antes do passo 3.

### 3. Criar (ou encontrar) o derivado

Nome canônico: `project-<nome-do-repo-alvo>`, normalizado do nome **real** do alvo.

Procure-o primeiro. Se não existir, crie-o **vazio** com `mcp__github__create_repository` e
empurre a casca do molde no primeiro commit — este ambiente não tem `gh` CLI e o MCP não cria a
partir de template; criar vazio e empurrar dá o mesmo histórico limpo. Se a criação for negada,
**pare** e instrua a criação manual em vez de improvisar um destino.

Não copie para o derivado: `.git/` do molde, `harness/runs|reports|state/` (evidência efêmera),
`workspace/` e `harness/change-proposals/*.yaml` — exceto `README.md` e `EXAMPLE-CP-001.yaml`.

As propostas do molde registram decisões tomadas **no molde**. Num derivado elas são história de
outro repositório: descrevem um caminho que aquele percorreu e este não, e citam IDs de um negócio
de exemplo que o **CP-000** remove logo em seguida. O derivado é dono da própria numeração a partir
do CP-000 que você cria no passo 5.

### 4. Ancorar

No derivado:

- `project.yaml` → `project.kind: derived` e o bloco `target` (`repo`, `ref`,
  `lock_source: target.lock`, `code_roots`, `languages`) do passo 2;
- `target.lock` → `kind: derived` e `target_sha` do passo 2. **O SHA mora só aqui.**

O schema reprova as duas metades: `derived` sem `target` não valida, e `target_sha` fora do
formato de commit não valida.

### 5. CP-000 — o derivado nasce sem código próprio

O molde carrega um negócio de exemplo (`src/project/`, `tests/unit/`) cuja única função é dar
substrato para as asserções do ADR-005 morderem. No derivado ele é ruído: metadado de um negócio
que não existe ali.

Abra **CP-000** no derivado propondo, **num só movimento** — porque separá-los deixa o
repositório vermelho no meio:

1. remover `src/project/`, `tests/unit/` e os metadados do exemplo (`CAP-PRICING`, `CAP-CATALOG`,
   `CMP-*`, `IFC-*`, `RULE-*`, `UI-*`, `REQ-*`, `MET-*`);
2. dar `superseded` no **ADR-005** — suas asserções apontam para `src/project/*` e viram
   `assertion_unresolvable` sem ele. Uma trava que não encontra o que vigiar está quebrada, não
   satisfeita;
3. ajustar `harness/stages.yaml`: os artefatos de `STAGE-CODE` e `STAGE-TESTS` passam a ser os do
   alvo, não os do molde;
4. remover a asserção **ADR-008-A6**. Ela crava `kind: "mold"` e diz respeito só ao repositório de
   origem — herdada aqui, reprovaria corretamente, porque aqui o kind é `derived`. O derivado não
   é o molde e não carrega as travas que falam só dele.

Risco `high` → o schema de change-proposal força `human_approval_required: true`. Espere o aval.

### 6. Encadear

Rode `/bootstrap` no derivado. Ele materializa `workspace/target/` no SHA do lock e valida.

## Pronto quando

- [ ] `python ci/validate_all.py` sai `0` no derivado
- [ ] `target.lock` tem o SHA e `project.yaml` **não** tem (ADR-008-A4 reprova se tiver)
- [ ] `code_roots` casa diretórios que existem de fato no workspace
- [ ] nem `ci/` nem `harness/` mencionam o alvo em lugar algum
- [ ] o alvo não recebeu nenhuma escrita
