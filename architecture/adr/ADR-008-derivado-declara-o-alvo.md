# ADR-008 — O derivado declara o alvo, nunca o copia; e nenhum alvo é especial

- **Status:** accepted
- **Data:** 2026-08-04
- **Riscos relacionados:** RISK-DERIV-001, RISK-DERIV-002

## Contexto

Este repositório é uma casca de governança madura e passiva. Ele tem schemas, fiscais, políticas e
asserções executáveis — e nenhum caminho de entrada. Quem clona não é levado a lugar nenhum, e a
camada mais valiosa do molde (`docs/COMO-ADOTAR.md`, passo 7, "popular a camada de metadados") é
justamente a única marcada como **opcional**.

Fechar esse vão exige responder onde os metadados de um repositório de negócio moram. Três opções,
e as duas primeiras falham por razões conhecidas:

1. **No próprio alvo.** Obriga a escrever no repositório que se quer auditar. O vigiado passa a
   hospedar o vigia — e a doutrina desta casa é literalmente que uma trava que o vigiado desliga em
   silêncio não é uma trava.
2. **Copiando o código do alvo para dentro do molde.** É o modo de falha do ADR-001 com outro
   objeto. Lá, copiar a régua permitiria remover uma linha da lista curada e o laudo passaria a
   dizer "nenhum achado" sem erro nem aviso. Aqui, a cópia deriva do original em silêncio, e o
   metadado descreve com toda a confiança um sistema que não existe mais.
3. **Num derivado que declara o alvo.** É esta decisão.

Há um segundo vão, mais sutil, e ele só aparece no segundo alvo. Um molde que resolveu o alvo
difícil de ontem cravando o nome dele num fiscal continua verde — para aquele alvo. Para os
demais, o caminho especial passa, o caminho geral nunca é exercitado, e a falha é indistinguível
de sucesso. A genericidade é o produto deste repositório; produto não se garante por disciplina.

## Decisão

**1. Três papéis, dois deles neste repositório.** `project.yaml:project.kind` ∈ `mold | derived`.
O molde não governa alvo algum; o derivado governa exatamente um, declarado em `target`. O schema
**exige** o bloco quando `derived` e o **proíbe** quando `mold`: um molde ancorado num alvo
específico deixou de ser genérico.

**2. O alvo é declarado e materializado, nunca versionado.** O código vive em `workspace/target/`
— efêmero, gitignored — no commit exato de `target.lock`. O derivado versiona só o que é dele.

**3. O SHA mora num lugar só.** `project.yaml` diz **qual** alvo e **onde** o SHA mora
(`lock_source: target.lock`); o número está apenas em `target.lock`. É `quality_standard.
version_source` → `requirements-qa.txt` aplicado ao alvo, e pela mesma razão: duas cópias de uma
versão derivam, e a comparação entre o que o metadado descreve e o que o alvo é hoje passa a
mentir. Um `file_lacks` reprova SHA de commit em `project.yaml`.

**4. Não há derivado a meio caminho.** O par `kind`/`target_sha` é travado nos dois sentidos:
molde não ancora SHA, derivado sem SHA não valida. Estado intermediário tolerado é estado
permanente, porque nenhum fiscal o reprova e ninguém volta para terminá-lo.

**5. Nenhum alvo é especial, e isso é fiscalizado.** `ci/` e `harness/` não mencionam nome, stack,
caminho ou URL de alvo algum. Tudo que é do alvo mora em `project.yaml:target`, em `target.lock` e
em `workspace/` — os três fora dos fiscais.

**6. Descobrir, nunca presumir.** `ref`, `code_roots` e `languages` são descobertos no
reconhecimento e declarados; nada vem de convenção — nem que a branch se chama `main`, nem que o
código mora em `src/`. E raiz declarada que não existe no alvo materializado é achado: um
`code_roots` chutado torna a invariante do código órfão verdadeira **por vacuidade**, o que é pior
que não tê-la, porque um fiscal que percorre conjunto vazio reporta verde.

## Consequências

- `project.yaml` de qualquer cópia anterior do molde deixa de validar até declarar `kind`. É
  deliberado: campo opcional aqui seria preenchido uma vez e nunca mais conferido — a mesma falha
  que a migração `metadata_version` 1.0 → 1.1 corrigiu em `classification`.
- Um derivado nasce carregando o negócio de exemplo do molde, que lá é ruído. Removê-lo é o CP-000
  do derivado, e ele **precisa** dar `superseded` no ADR-005 no mesmo movimento: as asserções do
  ADR-005 apontam para `src/project/*` e viram `assertion_unresolvable` sem ele.
- O reconhecimento do alvo continua sendo julgamento de agente. O fiscal verifica o declarado
  contra o materializado — reprova raiz inexistente, mas não descobre raiz esquecida. Quem fecha
  essa porta é a invariante do código órfão (ADR-009).
- Custo assumido: um alvo legítimo que precise de tratamento especial não pode recebê-lo no fiscal.
  Ou o tratamento vira capacidade genérica (um adapter novo, registrado), ou vira declaração no
  `target` daquele derivado. É a restrição que mantém o molde reaproveitável.

## Fiscal

`ci/validate_metadata.py::check_target_lock` (papel idêntico nos dois arquivos; âncora do SHA
apontando para `target.lock`); `ci/validate_metadata.py::check_target_roots` (raiz declarada existe
no alvo materializado); `harness/schemas/project.schema.json` (`derived` exige `target`, `mold` o
proíbe); `harness/schemas/target-lock.schema.json` (molde não ancora SHA; derivado exige commit
válido); `ci/audit_governance.py` (executa as asserções abaixo);
`harness/policies/adocao.md`; `.github/workflows/governance.yml`.
