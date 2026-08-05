# ADR-021 — O ledger é versionado, e a minimização mudou de lugar

**Status:** accepted · **Data:** 2026-08-05 · **Proposta:** CP-026

## Contexto

O item 5 do `governance/ripd.md` declara, como **medida de proteção de dados**, que
`harness/runs/`, `harness/reports/` e `harness/state/` não são versionados: *"a evidência não entra
no histórico do Git, de onde não se apaga."*

A consequência é que **nada sobrevive**. Os artifacts do CI expiram em 90 dias, e depois disso não
há como responder "quando este repositório esteve conforme?" nem "quantas vezes esta trava mordeu?".
Um sistema de governança sem memória mede o presente e esquece o passado.

## A promessa que era impossível

A primeira formulação desta decisão dizia que *"o schema proíbe campos de identificação pessoal"*.
Isso é tecnicamente infactível, e a autocorreção precisa ficar registrada:

- JSON Schema valida **estrutura**, não detecta PII em texto livre;
- pela definição da ANPD, **até um handle é dado pessoal** conforme o contexto.

Um schema que "proibisse PII" seria uma trava que não encontra o que vigia — satisfeita por
vacuidade, no sentido exato do ADR-006.

## Decisão

**`harness/state/ledger.jsonl` é versionado, e a medida de proteção migra do `.gitignore` para o
schema.**

`ledger.schema.json` não possui **nenhuma** propriedade textual livre. `additionalProperties: false`,
e cada campo é hash, SHA, ID opaco de run, enum, timestamp, ID de CP ou referência canônica de
artefato. Não existe campo onde nome, e-mail, login, URL de perfil, texto de prompt ou conteúdo de
laudo caibam.

**A diferença entre "proibido" e "inexpressável" é a diferença entre uma regra e uma trava.** Não
há detecção a fazer; há forma a respeitar.

Detalhes que carregam a decisão:

- `run_id` exclui `/`, `:` e espaço — sem isso aceitaria uma URL, e uma URL carrega organização,
  repositório e às vezes autor;
- `findings_digest` guarda o **digest** do laudo, não o laudo — é o que permite provar *"era este o
  conjunto de achados"* sem trazer o conteúdo, que é onde o dado pessoal do alvo auditado moraria;
- `artifact_ref` é ancorado em prefixo conhecido, para não virar caminho arbitrário;
- `actor_ref` é pseudonimizado (`^anon:[0-9a-f]{16}$`), com a tabela de reidentificação **fora
  deste repositório**. Versioná-la aqui recriaria o problema que a pseudonimização resolve.

**O ledger é deliberadamente mais estrito que `business.stakeholders`**, que aceita handle. A razão
está nas palavras do próprio RIPD: o ledger é append-only e versionado — *de onde não se apaga*.
Minimização suficiente num arquivo editável vira exposição **permanente** num histórico imutável.

## Append-only por diff

Um ledger que se pode reescrever não é ledger. `ci/audit_ledger.py` compara as linhas com as do
commit anterior: qualquer linha preexistente alterada ou removida reprova.

É o modo de falha mais tentador de todos, porque **a linha que alguém quer mudar é sempre a que
anotou um vermelho**. A correção é acrescentar uma linha nova; nunca editar a antiga. O registro é
o que aconteceu, não o que se preferia.

Sem git disponível, o estado é **indeterminado** — o fiscal diz isso e não afirma append-only que
não pôde verificar.

## Consequências

O item 5 do RIPD foi **atualizado no mesmo PR** — mudar uma medida de proteção declarada sem tocar
no documento que a declara é exatamente o que este repositório recusa em toda parte. A exceção está
escrita lá, com o motivo e o mecanismo.

`harness/runs/` e `harness/reports/` continuam gitignored. A exceção é de **um arquivo**, não da
regra.

## Fiscal

`ci/audit_ledger.py::check_append_only` e `::check_linhas_validas`, mais
`harness/schemas/ledger.schema.json`. As asserções `ADR-021-A*` provam que o schema continua sem
campo livre e que o fiscal continua existindo.
