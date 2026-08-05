# ADR-026 — A árvore taggeada valida-se pela cadeia, não por `validate_all`

**Status:** accepted · **Data:** 2026-08-05 · **Proposta:** CP-034
**Convive com:** ADR-008 (que não é tocado), ADR-015, ADR-025

## Contexto

`python ci/validate_all.py` reprova no commit taggeado da v1.0.0. Hoje, sob o **ADR-008-A5**: o
manifesto carrega `run_url`, que é uma URL de repositório dentro de `harness/`.

```
[high] FIND-ADR-008-A5
harness/releases/v1.0.0.manifest.json contém o padrão que a decisão proíbe:
/github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/
```

Duas consequências que ninguém tinha visto:

**O job `auditar` não tinha como ficar verde.** Ele rodava `validate_all.py` na árvore da tag. Não
apareceu na v1.0.0 só porque ref criada com `GITHUB_TOKEN` não dispara workflows — a primeira tag
que chegasse por outro caminho encontraria um job estruturalmente reprovado. E é exatamente aí que
auditar importa.

**A frase "release nasce só de commit validado" era mais estreita do que soava.** Verdadeira sobre
o **pai**; falsa sobre a árvore publicada. A distinção existia no desenho desde o CP-021 e nunca
tinha sido enunciada.

## Decisão

**A árvore taggeada não se valida por `validate_all.py`. Ela se valida pela cadeia.**

| Árvore | Pergunta certa |
|---|---|
| um commit qualquer, a `main` | `python ci/validate_all.py` |
| a árvore **taggeada** | pai verde · `diff pai..tag` só o manifesto · `--verify-tag` |

Não é afrouxamento — é dizer o que já era verdade. O manifesto descreve a validação do **pai**, e o
elo que exige *"o commit de release não muda nada além do manifesto"* é o que **transporta** essa
validação para a árvore publicada. Rodar `validate_all` na tag sempre foi perguntar a pergunta
errada para aquela árvore.

**`validate_all.py` permanece puro e cego a refs.** A semântica da tag mora aqui e no job, nunca no
fiscal. Um fiscal que soubesse em qual ref está passaria a ter duas respostas para a mesma árvore, e
a diferença entre "violação" e "não consegui olhar" — que esta casa separa por desenho — ficaria
dependente de onde o `HEAD` estava.

### O job `auditar`, na ordem que a decisão exige

1. recusar tag movida;
2. `--verify-tag` — **enquanto a tag está montada**, porque ele lê o manifesto do disco;
3. `git switch --detach` no pai;
4. `validate_all.py`, `pytest tests/governance`, `audit_mutations.py` — na árvore para a qual essas
   são as perguntas certas.

### Cláusula A — o manifesto para de carregar URL de repositório

`run_url` sai de `build_manifest` e do CLI. Não é *"proibido escrever"*: **não existe mais caminho
que produza o campo** — a mesma formulação da CP-026, e pela mesma razão, porque proibição depende
de alguém lembrar. O dado não se perde: `repository` + `run_id` reconstroem a URL.

**O schema continua aceitando o campo, de propósito.** O manifesto da v1.0.0 é registro histórico e
precisa seguir válido sob o schema que o governa. Registro que se invalida quando a regra muda deixa
de ser registro.

### Cláusula B — o manifesto não entra na árvore validada

`harness/releases/` contém **apenas** `README.md`. Asserção própria, para reprovar pelo **motivo** e
não por efeito colateral do A5 — quando um manifesto é plantado ali, as duas travas acusam, com
mensagens distintas e por razões distintas. Decisão dupla, não redundância cega.

### Cláusula C — o ADR-008-A5 não é tocado

Nem alargado, nem afrouxado, nem excluído. Uma asserção prova: se alguém acrescentar `exclude:` ao
bloco do A5 para acomodar manifestos, ela reprova. Afrouxar um fiscal para o CI passar é a terceira
opção, e é a errada.

## O achado que a cláusula B evitou

A forma óbvia da cláusula B seria `path_absent` com glob — e ela é uma **armadilha**:

`assert_path_absent` usa `rel_exists`, que é **literal**. `harness/releases/*.manifest.json` nunca
"existiria", e a asserção passaria sempre. Pior, e é isto que a torna perigosa: a mutação canônica
`criar_caminho` criaria um arquivo chamado **literalmente** `v*.manifest.json`, `rel_exists` o
encontraria, a asserção ficaria vermelha depois de mutada — e a **prova de mutação certificaria uma
trava decorativa**.

> **Um fiscal de fiscais enganado é pior que fiscal nenhum, porque produz um selo.**

Daí o tipo novo, `dir_allowlist`: ele **enumera** o que está no diretório em vez de perguntar por um
nome que precisaria adivinhar, e seu inverso canônico — pôr qualquer outra coisa lá dentro — é
honesto. Registrado também em `harness/policies/prova-de-mutacao.md`.

## Nota sobre a v1.0.0

Ela **não é re-emitida** e **não ganha mecanismo de exceção**.

O manifesto dela carrega `run_url`, então `validate_all.py` reprova na sua árvore taggeada. Depois
deste ADR isso deixa de ser contradição e passa a ser uma **pergunta que não se faz àquela árvore**.
A cadeia dela está íntegra e continua verificável:

```
✓ cadeia íntegra: v1.0.0 → 5631106937d7 → harness/releases/v1.0.0.manifest.json → 8d5986b6ad3c
```

pai `9b8071c` verde, `diff pai..tag` só o manifesto, `--verify-tag` exit 0. A nota mora aqui e não
num arquivo de exceções: exceção declarada em lista vira lista que cresce.

## Consequências

O job `auditar` passa a poder ficar verde — e, com isso, a auditoria de tags que chegam por fora
deixa de ser um passo que nunca executou com sucesso.

"Release nasce de commit validado" passa a ser verdadeira na semântica que este ADR publica: o
commit validado é o pai, a validação é `validate_all` nele, e a cadeia é o que a transporta para a
árvore que carrega a versão.

## Fiscal

`.github/workflows/release.yml` (job `auditar`), `ci/audit_governance.py::assert_dir_allowlist`,
`ci/mold_release.py::verify_chain`. As asserções `ADR-026-A*` provam a ordem do job, a ausência do
caminho que produzia `run_url`, a lotação fechada de `harness/releases/` e a integridade do
ADR-008-A5.
