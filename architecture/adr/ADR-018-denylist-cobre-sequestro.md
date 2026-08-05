# ADR-018 — A denylist cobre sequestro, não só auto-autorização

**Status:** accepted · **Data:** 2026-08-05 · **Proposta:** CP-025

## Contexto

`env_hygiene` nasceu respondendo a uma ameaça concreta e bem identificada: os gates da WebQA Suite
são fail-closed **por variável de ambiente**, e um agente com shell pode exportá-las. Daí
`env_denylist_prefix: ["WEBQA_"]` e `fail_on_denied_env: true`.

A lista está certa e continua valendo. Mas ela foi escrita olhando para **auto-autorização** — o
processo se dando uma permissão que não tem. Existe uma segunda família de variáveis que não
autoriza nada, e que por isso mesmo é pior: ela não precisa de permissão nenhuma para agir.

| Variável | O que ela faz |
|---|---|
| `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY` | reescrevem o destino de toda requisição do job — inclusive as do `pip` |
| `PIP_INDEX_URL`, `PIP_EXTRA_INDEX_URL` | trocam o índice de pacotes: o pin exato continua exato e passa a apontar para outro lugar |
| `PYTHONPATH`, `PYTHONSTARTUP` | injetam código no interpretador **antes** de qualquer linha deste repositório rodar |
| `NODE_OPTIONS` | o mesmo, do lado JS, via `--require` |

O padrão é único, e é o que justifica tratá-las juntas: **nenhuma delas ataca o fiscal — elas
trocam o que o fiscal lê.** Um fiscal que importa `harness_lib` sob `PYTHONPATH` alheio importa o
`harness_lib` de outra pessoa, executa, e reporta verde com convicção.

Verde com convicção é estritamente pior que vermelho, porque encerra a investigação.

## Decisão

`env_denylist_exact` entra em `harness.yaml` com os nove nomes, ao lado do prefixo já existente. O
guard é `ci/env_guard.py`, e roda em ambos os workflows — no `qa.yml` **antes do `pip`**, porque
verificar depois seria conferir a fechadura com o ladrão já dentro.

**A lista é derivada, nunca duplicada.** O workflow não a repete: `env_guard.py` a lê de
`harness.yaml`. Uma segunda cópia derivaria em silêncio, e a primeira entrada a divergir seria
justamente a que alguém removeu. É a lição do CP-020, e é o que faz uma variável nova nascer
coberta.

**A exceção é declarada, não subtraída.** `PYTHONPATH` é legitimamente necessário nos testes de
mordida, que rodam um fiscal a partir de uma cópia mutada do repositório e precisam apontar o
subprocesso para o `ci/` dessa cópia. A resposta certa não é tirar `PYTHONPATH` da lista — seria
desligar a trava para acomodar um caso — mas declarar a exceção em `env_hygiene.exceptions`, com
nome, **contexto** e justificativa.

O contexto é o que torna a exceção honesta: quem invoca o guard precisa declarar em que contexto
está, e só as exceções daquele contexto são dispensadas. Uma exceção sem contexto valeria em toda
parte — e uma exceção que vale em toda parte é a entrada removida da lista com outro nome.

**Exceção declarada é exceção contestável numa revisão. Entrada removida é exceção que ninguém mais
vê.**

## Consequências

Um workflow, uma action de terceiro ou um passo anterior escrevendo em `$GITHUB_ENV` deixam de
poder redirecionar de onde vem o código que os fiscais executam sem que o CI acuse.

O custo é um passo por job, de milissegundos, sem rede. E um atrito real: quem precisar de uma
dessas variáveis terá de declarar a exceção — o que é o objetivo, não o efeito colateral.

## Fiscal

`ci/env_guard.py::violacoes` (função pura, testável sem ambiente real), aplicado por
`.github/workflows/qa.yml` e `.github/workflows/governance.yml`, com passo negativo que injeta
`HTTP_PROXY` e exige o abort. O hook `ci/hooks/pre_bash_env_hygiene.py` estende a mesma lista à
sessão do agente — a trava que só existe no CI não protege onde o agente tem shell.
