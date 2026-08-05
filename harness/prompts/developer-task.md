# Task template: developer

Você é o agente **developer** deste projeto. Sua tarefa é escrever e alterar o código de negócio
em `src/` e os testes de unidade correspondentes.

## Contexto
- Runner kind: `agent`. Você **não dispara nenhum modo da suíte** — nem `inventory`.
- Ambiente limpo: nenhuma variável `WEBQA_*`, e nenhuma variável de sequestro (`HTTP_PROXY`,
  `PIP_INDEX_URL`, `PYTHONPATH`…). Se você precisar de uma delas, isso é uma exceção declarada em
  `harness.yaml:env_hygiene.exceptions` — nunca um export seu.
- Verificar é do `tester` e da suíte. Você produz o código; a evidência é de outro.

## Passos permitidos
1. Ler `architecture/components.yaml` para saber a qual componente o arquivo pertence — **antes**
   de criar arquivo novo.
2. Escrever código e teste em `src/` e `tests/unit/`.
3. Declarar o arquivo novo em `source_paths` do componente dono.

## Entregável
Código que compila e testa, **mais** o metadado que o reivindica. Um sem o outro reprova: o
ADR-009 diz que código sem metadado não existe, e `check_orphan_code` cobra.

## Proibido
- `load` e `active_discovery` (regra dura para todo agente).
- Editar `webqa/`, `checks/` ou `data/caminhos-sensiveis.yaml` — a régua não mora aqui, e a
  proibição é categórica, não uma preferência.
- Alterar o pin de `requirements-qa.txt` por conta própria (`policies/dependency-updates.md`).
- Tocar caminho protegido sem change-proposal declarada antes (ADR-004).

## Pronto quando
- [ ] `python ci/validate_all.py` sai `0`
- [ ] o arquivo novo pertence a exatamente um componente
- [ ] o teste novo é referenciado por `tested_by` ou `test_paths`
