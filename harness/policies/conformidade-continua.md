# Política: conformidade contínua — verificar não é validar

Duas perguntas diferentes moram neste repositório, e confundi-las é o erro que esta política
existe para evitar.

| | Pergunta | Quem responde | O que faz com um achado |
|---|---|---|---|
| **Verificação** | está conforme o declarado? | fiscais determinísticos | reprova o CI |
| **Validação** | o declarado ainda é verdade? | agente `conformance` | **propõe** |

Onze ADRs de fiscais respondem muito bem a primeira. Nenhum responde a segunda: a descrição de um
componente pode ter sido escrita quando ele fazia outra coisa; um ADR `accepted` pode ter todas as
asserções verdes e registrar uma decisão que deixou de fazer sentido; um risco `mitigated` pode
citar um controle que existe, tem caminho válido, e não mitiga mais nada.

## O agente nunca corrige

Todo achado sai como `change_proposal`, `risk_entry` ou `accepted`. Nunca como um diff.

Um agente que conserta o que ele mesmo julga é **juiz e parte**: a correção entra no repositório
sem que ninguém tenha revisado o julgamento que a originou, e o julgamento desaparece — sobra só o
diff, que parece uma mudança comum. Separar as duas coisas é o que mantém o julgamento auditável.

`accepted` **exige** `rationale`. Aceitar em silêncio é como um achado morre.

## O fiscal não lê a prosa; cobra o frescor dela

`check_review_currency` não julga se a descrição condiz com o código — confere que alguém julgou e
que o julgamento cobre **este** estado. É o mesmo desenho de `check_judgment_currency` para
privacidade: fiscal determinístico não sabe julgar, mas sabe muito bem dizer se o julgamento é
velho.

## O fingerprint inclui o SHA do alvo

`conformance_fingerprint()` cobre dez arquivos de metadado governável **mais** `target.lock`.

Sem o SHA, o alvo inteiro pode ser reescrito enquanto o metadado fica idêntico — e a revisão
continuaria se declarando fresca, descrevendo com toda a confiança um sistema que já mudou. Com
ele, **avançar o lock invalida a revisão**. Isso é intencional, e é o gatilho que `/sincronizar`
torna visível.

O escopo deliberadamente **não** inclui `docs/` nem laudos: um artefato derivado mudar não reabre
julgamento algum — ele só reflete o que já mudou.

## Drift vira trabalho, não um número

```bash
python ci/bootstrap.py --check-drift            # o alvo andou? quanto?
python ci/audit_conformance.py --sync-diff SHA  # o que fica velho se o lock avançar?
```

A resposta útil não é "o alvo andou 40 commits" — é "estes seis itens descrevem arquivos que
mudaram". E o `--sync-diff` **não avança o lock**: avançá-lo é decisão declarada em
change-proposal, porque decidir se um item ainda vale é julgamento, não diff.

## O canal de retorno nasce fechado

`harness.yaml:target_feedback.open_issues_on_target` é `false`. É a única capacidade deste
repositório que escreveria num repositório de terceiro, e nascer desligada é coerente com
`decision_policy.default: deny`. Ligado, um fiscal novo e ruidoso vira issue de verdade no projeto
de outra pessoa.

## Limite honesto

O workflow semanal é **best-effort**. Um agendamento que falha em silêncio não pode ser a única
linha de defesa, e não é: o gate continua sendo `governance.yml` a cada push. O semanal existe
para pegar o que só o tempo revela — drift do alvo, julgamento envelhecido — não para substituir
o gate.

E a qualidade do julgamento do agente não é fiscalizável. O que a máquina cobra é forma e frescor:
que a revisão exista, cubra este estado, encaminhe cada achado e declare o que **não** avaliou.

---

Fiscalizado por: `ci/audit_conformance.py::check_review_currency` (revisão existe, cobre este
estado incluindo o SHA do alvo, e nenhum encaminhamento fica sem destino);
`harness/schemas/conformance-review.schema.json` (`accepted` ⇒ `rationale`; `not_assessed`
obrigatório); `harness/schemas/harness.schema.json` (`target_feedback` declarado);
`.github/workflows/conformance.yml`; `.github/workflows/governance.yml`.
Declarado em: `governance/conformance-review.yaml`, `architecture/adr/index.yaml`,
`harness/agents/conformance/`, `harness/harness.yaml`.
Falha como: revisão ausente, vencida ou com encaminhamento sem destino ⇒ achado e exit 1;
metadado ilegível ⇒ exit 2.
