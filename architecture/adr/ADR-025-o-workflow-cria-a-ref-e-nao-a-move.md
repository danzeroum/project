# ADR-025 — O workflow cria a ref, e não pode movê-la

**Status:** accepted · **Data:** 2026-08-05 · **Proposta:** CP-031
**Revê:** a decisão registrada em comentário no `.github/workflows/release.yml` (CP-021)

## Contexto

O CP-021 fechou o `release.yml` com esta frase, em comentário:

> *"O que este workflow NÃO faz, deliberadamente: criar a tag. A tag é criada por quem decide
> publicar, e o workflow a AUDITA. Um workflow que criasse a própria tag que ele valida seria o
> vigiado assinando o próprio atestado."*

O argumento é bom e está errado por uma razão que só apareceu quando alguém tentou publicar de
verdade: **o que sobrou para "quem decide publicar" foi `git tag` manual.** E `git tag` manual
pode ser apontado para qualquer commit — inclusive um que nunca passou por validação alguma. O
workflow audita *depois*, mas auditar depois de publicar é descobrir o problema com o problema já
publicado. A tag existe, foi vista, e derivados podem tê-la consumido no intervalo.

Trocamos "o vigiado assina o próprio atestado" por "qualquer commit pode virar versão e a gente
descobre em seguida". A segunda é pior.

## Decisão

**A ref nasce do workflow de release, depois da validação, e o workflow não pode movê-la.**

### A assimetria que responde à objeção original

Criar e mover são operações diferentes, e só a segunda é a que o argumento do auto-atestado teme.

| Operação | Quem pode | Por quê |
|---|---|---|
| **criar** `refs/tags/vX.Y.Z` | o workflow, após validação total + testes + prova de mutação | `git push` de ref inexistente |
| **mover** `refs/tags/vX.Y.Z` | ninguém, por este caminho | `git push` sem `--force` recusa atualizar tag existente |
| **impedir mover** de qualquer outro caminho | ruleset administrado **fora** daqui | ainda não existe — `RISK-EXT-001`, `due: 2026-11-03` |

O que o workflow assina é **"esta versão nasceu de um commit validado"**. Isso ele pode provar: ele
rodou a validação, e o objeto que empurra é o mesmo que verificou. O que ele **não** assina é
*"esta versão continua sendo o que eu disse"* — essa afirmação exige uma autoridade que não pode
ser desligada por quem edita o workflow, e continua sendo do ruleset externo.

### A janela entre validar e criar, fechada por construção

O limite de maior risco deste caminho não é a validação nem a verificação: é o **intervalo** entre
as duas. Se algo mudar nele, a tag certifica uma árvore que nenhuma validação viu, com o carimbo de
uma que viu outra.

A janela foi fechada tornando-a **vazia**, não vigiando-a. Tudo acontece nos objetos locais do
runner:

```
P (validado)  →  emite manifesto  →  R = commit de release  →  tag local  →  verify-tag
                                                                                  ↓
                                                                        git push refs/tags/vX.Y.Z
```

O que é publicado é, byte a byte, o que foi verificado — porque é o mesmo objeto Git. O push é a
única operação remota, e é a última.

`ci/mold_release.py::preflight_publicacao` é a segunda tranca, e é função pura: recusa tag
preexistente, `HEAD` movido entre a validação e a publicação, e manifesto já presente na árvore do
commit validado — este último porque, se ele já estivesse lá, o elo *"o commit de release não muda
nada além do manifesto"* passaria por **vacuidade** em vez de por verificação.

### O que a validação significa neste caminho

Três passos, e nenhum é opcional:

1. `python ci/validate_all.py` — o mesmo comando que o `governance.yml` roda, travado como `const`
   no schema do manifesto para que afrouxá-lo aqui não passe despercebido.
2. `pytest tests/governance -q` — os fiscais mordem.
3. `python ci/audit_mutations.py` — **as travas ainda mordem** (ADR-024). Sem este passo, uma
   versão sairia sem evidência de que as regras bloqueantes ainda bloqueavam naquele commit. Para
   um molde cujo produto *é* o conjunto de travas, era a lacuna mais séria das três.

Qualquer um vermelho ⇒ **nenhuma ref nasce**. Não existe release parcial.

## Duas consequências que precisam ficar escritas

**Uma ref criada com `GITHUB_TOKEN` não dispara outros workflows.** O job de auditoria por push de
tag **não** roda para a tag que o dispatch criou. Por isso o próprio dispatch verifica a cadeia
antes de publicar: contar com o push-audit seria contar com um passo que não executa. O job de
push continua existindo — ele cobre a tag que chegue por qualquer outro caminho, que é justamente
o caso em que auditar importa.

**O manifesto fica na árvore do commit taggeado, não na `main`.** `harness/` é caminho protegido e
o ruleset da `main` recusa push direto para todos. Um workflow que escrevesse lá estaria fazendo
por fora o que esta casa exige que se faça por PR. O mesmo vale para a linha do ledger, que vai
para uma branch própria e entra pelo portão normal.

## Consequências

Publicar deixa de ser um gesto (`git tag`) e passa a ser um **evento com pré-condições**. O custo é
um dispatch em vez de um comando local; o ganho é que a categoria *"tag apontando para commit não
validado"* deixa de ser representável por este caminho.

O que continua fora do alcance daqui está declarado, não escondido: enquanto não houver ruleset de
tag administrado externamente, a imutabilidade da âncora é risco aceito **com data**, e o eixo de
tags de `ci/verify_protection.py` o reporta a cada publicação.

## Fiscal

`.github/workflows/release.yml` (job `publicar`), `ci/mold_release.py::preflight_publicacao`,
`ci/verify_protection.py::verify_tag_protection`. As asserções `ADR-025-A*` provam que a ordem dos
passos continua sendo a decisão — inclusive uma que exige, por regex, que a prova de mutação
apareça **antes** do `git push` da ref.
