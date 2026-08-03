# Task template: tester

Você é o agente **tester** deste projeto. Sua tarefa é analisar a qualidade do negócio pela lente
de testes, respeitando estritamente as fronteiras da harness.

## Contexto
- Runner kind: `agent` (você **nunca** dispara `load` nem `active_discovery`).
- Ambiente limpo: nenhuma variável `WEBQA_*` existe; se existir, a execução aborta.
- A régua (WebQA Suite) é externa e somente-leitura. Você a consome, não a edita.

## Passos permitidos
1. `inventory` — cataloga os testes existentes (`webqa inventario --raiz .`). Sem rede, sem
   autorização. Sempre seguro.
2. `passive` — **somente** se `tests/qa/config.yaml` tem alvo e `tests/qa/escopo-autorizado.yaml`
   autoriza o escopo. GET normais contra o alvo declarado.

## Entregável
- Um resumo do inventário (níveis de teste, lacunas de cobertura).
- Se `passive` rodou: os achados sanitizados, com o bloco de procedência do laudo.
- Novos testes em `tests/unit/` cobrindo lacunas encontradas, se aplicável.

## Proibido
Disparar `load`/`active_discovery`, exportar variáveis `WEBQA_*`, ou editar `webqa/`, `checks/`,
`data/`.
