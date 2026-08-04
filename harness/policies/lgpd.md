# Política: privacidade e LGPD, sempre, em dois níveis

A análise de privacidade não é etapa final nem pedido sob demanda: roda a cada push, sobre o
projeto inteiro. Mas ela roda em **dois níveis**, e confundi-los é o erro que produz falsa
conformidade.

> **O fiscal determinístico não julga legalidade. Ele garante que o julgamento existe, é do tipo
> certo, e cobre exatamente este estado do repositório.**

## Nível 1 — determinístico (`ci/audit_lgpd.py`)

O que a máquina consegue afirmar sem opinar:

- **Registro das operações (Art. 37).** Todo campo com forma de dado pessoal está em
  `governance/data-inventory.yaml`, com finalidade, base legal, retenção e componente dono.
- **Varredura de tratamento-sombra.** A superfície é derivada de `harness/stages.yaml`
  (`privacy_lens.scan`), nunca hard-coded no fiscal. Identificador com forma de PII fora do
  inventário é achado.
- **Coerência da declaração.** `project.yaml:classification.lgpd_relevance` e
  `data-inventory.controller.role` contam a mesma história — a mesma verdade em dois lugares
  já divergiu antes de alguém perceber.
- **Direitos do titular (Art. 18).** Com inventário não-vazio, os quatro endpoints são exigidos.
  Não existe direito do titular sem endpoint: sem onde exercer, o direito não existe no sistema.
- **Frescor do julgamento (Art. 38).** Ver abaixo.

Duas travas que **não** são runtime, e sim estruturais no schema — a violação não pode ser
escrita, então não precisa ser detectada:

- Dado `sensivel` não admite `legitimo_interesse` nem `protecao_credito` (Art. 11): o `then` do
  `if/then` restringe o enum da base legal, exige `art_11_category` e `masked_at_rest: true`.
- Papel de controlador/operador exige `dpo_contact` (Art. 41).

## Nível 2 — julgamento (skill `/revisao-lgpd`, agente `privacy`)

O que exige juízo e **não** deve ser simulado por heurística: adequação da base legal à
finalidade; proporcionalidade do prazo de retenção (Art. 6º, I e III); se um DTO devolve além do
necessário; granularidade do consentimento; validade do mecanismo de transferência internacional;
plano de resposta a incidente e SLA à ANPD (Art. 48); severidade P0–P3; e — o mais importante —
**se um campo que a heurística não sinalizou é ainda assim dado pessoal** (um `sku` que codifica
pessoa, um `id` de sessão reidentificável). Heurística encontra formas conhecidas; afirmar o
contrário seria vender falso negativo como conformidade.

O produto vai em `governance/ripd.md` (prosa) e `governance/privacy-review.yaml` (registro
tipado). Separar os dois é o que permite fiscalizar sem tentar fiscalizar prosa.

## Frescor por fingerprint, nunca por data

`ci/audit_lgpd.py` compara o `scope_fingerprint` registrado com o atual. É hash de conteúdo, não
data nem `git log`: `actions/checkout@v4` clona com `fetch-depth: 1`, então histórico não existe
no CI, e data tornaria o resultado irreprodutível. Mesmo idioma do `sensitive_paths_hash`
(ADR-003).

O escopo é **proporcional**: inventário, o bloco `classification` de `project.yaml`,
`tests/qa/config.yaml` e os arquivos com achado de PII. Refatorar precificação não reabre o
julgamento; introduzir um campo de CPF reabre.

## A régua desta verificação

Os léxicos de dado pessoal e sensível são constantes em `ci/audit_lgpd.py`, deliberadamente não
um YAML de configuração — uma lista curada que o fiscalizado edita pelo caminho de menor
resistência para de procurar o que dava trabalho, e o laudo continua dizendo "nenhum achado".
Suprimir é **declarar** em `data-inventory.yaml:scan.exclusions` com justificativa; e `ci/` é
`protected_path`, então mudar a lista exige revisão. Isenção que não suprime nada é achado.

Checks profundos de LGPD pertencem, no longo prazo, à suíte externa (que já expõe o marcador
`lgpd`): régua fora, comparável entre projetos. O que mora aqui é o que só o consumidor sabe.

---

Fiscalizado por: `ci/audit_lgpd.py`; `harness/schemas/data-inventory.schema.json` (Art. 11 e
Art. 41 como trava `if/then`); `harness/schemas/privacy-review.schema.json`;
`harness/schemas/project.schema.json` (`classification` obrigatório, com enums);
`.github/workflows/governance.yml`.
Declarado em: `governance/data-inventory.yaml`, `governance/privacy-review.yaml`,
`governance/ripd.md`, `harness/agents/privacy/AGENT.md`.
Falha como: PII fora do inventário, direito sem endpoint, papel divergente ou julgamento vencido
⇒ achado com artigo da LGPD e princípio PbD, e exit 1.
