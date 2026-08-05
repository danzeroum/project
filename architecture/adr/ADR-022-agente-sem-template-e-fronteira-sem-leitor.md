# ADR-022 — Agente sem template é fronteira sem leitor

**Status:** accepted · **Data:** 2026-08-05 · **Proposta:** CP-027

## Contexto

`harness/agents/` declara contratos para sete agentes: o que cada um pode disparar, o que nunca
pode, e qual é o runner kind. São fronteiras cuidadosamente escritas.

`harness/prompts/` tinha **três** templates.

Os quatro agentes sem template não estavam menos definidos — estavam definidos **só no contrato**.
E o contrato não é o que se lê no momento de invocar o agente; o template é. Quem for invocar um
agente sem template improvisa a instrução, e improvisar a instrução de um agente que pode editar
metadado é exatamente onde a fronteira declarada no `AGENT.md` deixa de valer: ninguém a repetiu no
lugar onde ela seria lida.

## Decisão

**Todo agente tem template, e todo template tem agente.** As duas direções, porque pegam coisas
diferentes:

- **agente sem template** → a fronteira existe e não é lida;
- **template sem agente** → **agente-fantasma**: instrução viva para um papel que não existe mais,
  ainda invocável, com proibições que ninguém mantém.

### A correspondência é lida do `inputs.md`, nunca do nome do arquivo

Esta é a parte que exigiu olhar o repositório antes de decidir. Uma convenção `<agente>-task.md`
seria natural — e falsa aqui: `review-task.md` é do `reviewer`, `lgpd-task.md` é do `privacy`. Os
dois são citados por ADRs, pelo registro de riscos e pelos próprios `inputs.md`.

Adotar a convenção de nome obrigaria a **renomear artefatos que outros fiscais já citam** — trocar
a realidade para caber na regra, em vez do contrário. O `inputs.md` de cada agente já declarava seu
template; o fiscal passa a ler **de lá**. Os quatro agentes que faltavam ganharam a linha.

## Documentação viva dos schemas

`ci/generate_schema_docs.py` deriva `docs/schema-reference.md` dos próprios schemas, com `--check`
**bloqueante** — o padrão desta casa, e a razão do R-11 ter rejeitado "docs não-bloqueantes":
documentação que pode ficar desatualizada sem custo **fica** desatualizada, e passa a mentir com a
autoridade de documentação.

O gerador só desce em objetos e itens de array. Descer em `allOf`/`if`/`then` produziria caminhos
que não existem em documento nenhum, e um índice que descreve campos inexistentes é pior que um
índice incompleto: ele manda o leitor procurar o que não há.

O arquivo nasce com o cabeçalho canônico do CP-029 e entrou **sozinho** na cobertura de
`check_derived_vs_source` — que é a prova de que aquele fiscal foi construído para derivar do
diretório, e não para conhecer dois arquivos.

## Prontidão é modo, não script novo

A proposta original era `/verificar-pronto`, rejeitada no R-10 por duplicar o que `orient.py` já
sabe — e por errar o caminho do lock ao duplicar. `orient.py --pronto` reusa `papel()`,
`fiscais_agora()` e `cobertura_do_alvo()`: as mesmas funções, então não há segunda resposta que
possa divergir da primeira.

E ele **não reprova**, como nada naquele arquivo. O ADR-014 decidiu que um orientador que também
fiscaliza vira o oitavo fiscal, sem política e sem teste de mordida. `--pronto` responde *"o que
falta"*; quem reprova é `validate_all.py`.

## Consequências

Um agente novo passa a exigir template, e um template órfão passa a reprovar. O custo é um arquivo
a mais por agente — e é o arquivo que carrega a fronteira até quem a executa.

## Fiscal

`ci/audit_governance.py::check_agent_prompt_pairing` (bidirecional, lido dos `inputs.md` reais);
`ci/generate_schema_docs.py` com `--check` dentro de `validate_all.py`; `ci/orient.py::pronto`.
