# Política: segurança como departamento

Dos departamentos que este repositório governa, `architecture/`, `business/`, `design/` e
`governance/` existiam como camada — com schema, fiscal e etapa. **Segurança não existia.** Estava
difusa num `security_owner` em `project.yaml` e num punhado de riscos escritos sobre a própria
harness.

Era a maior lacuna estrutural restante, e do tipo que não aparece em CI verde nenhum — porque nada
a procurava. É a mesma família de silêncio que a Fase E descobriu: ausência não reprova, a menos
que alguém escreva a trava que pergunta pelo que falta.

## Duas travas do modelo de ameaças

**Toda ameaça exige ao menos uma mitigação.** Ameaça catalogada e não tratada é o `to-be-assessed`
do ADR-002 vestido de diligência: parece trabalho de segurança, enche um documento, e não obriga a
nada.

**Toda ameaça exige `residual_risk` apontando para um `RISK-*` real.** É o que impede a segurança
de virar uma ilha. Com o residual ancorado, a ameaça herda **dono, prazo e a cobertura reversa da
Fase E** — se o risco estiver `open` sem prazo, R2 acusa; se um ativo de alto risco não for
referenciado, R1 acusa. Sem o residual, o modelo de ameaças seria um arquivo que só o autor lê.

E o `target` resolve contra componentes, interfaces e superfícies reais. Ameaça contra componente
inexistente é trava que não encontra o que vigiar — quebrada, não satisfeita (ADR-006).

## O inventário de dependências

Mesma direção reversa. Os fiscais já sabiam que a régua está pinada com `==`; ninguém verificava
que **toda** dependência declarada em `pyproject.toml` e `requirements-qa.txt` está inventariada,
com dono e razão.

Agora, dependência declarada e não inventariada é achado — e entrada inventariada que ninguém
declara também, porque faz o inventário parecer mais completo do que é.

Duas decisões de leitura merecem registro:

- **Textual, não resolvida.** Não usamos `tomllib` nem consultamos o ambiente. O que interessa é
  o que o repositório **declara**, não o que está instalado na máquina de quem roda: um inventário
  conferido contra o `site-packages` local passaria ou reprovaria conforme o computador, que é o
  oposto de fiscalizável.
- **`pin_kind` descreve o que É, não o que deveria ser.** `range` declarado é uma decisão
  auditável; `range` escondido é uma dependência que muda sozinha entre dois runs. O fiscal não
  exige `exact` em tudo — exige que a escolha esteja escrita.

## Nada de julgamento automático

`severity` aceita `pending_judgment` pela mesma trava da Fase D: nenhuma ferramenta decide
gravidade de ameaça, e o sentinela é recusado em documento promovido. Um scanner que atribuísse
severidade produziria a pior combinação possível — julgamento de máquina com aparência de análise
humana.

## Limite honesto

Este molde não tem runtime. `THREAT-PRICING-INFO` traz uma mitigação `accepted` dizendo exatamente
isso: não há log de produção aqui, e o derivado que governar um alvo com serviço **herda a ameaça
e precisa de mitigação real**. Registrar a herança é o oposto de fingir cobertura.

E o modelo de ameaças é escrito por gente. Nenhum fiscal descobre a ameaça que ninguém pensou —
o que ele garante é que a pensada não fica sem tratamento, sem residual e sem dono.

## O que pode ser ameaçado (CP-019)

Uma ameaça aponta para um componente, interface ou superfície do sistema governado — **ou para uma
etapa do harness** (`STAGE-*`), quando o ameaçado é a própria máquina de governar.

A segunda namespace não é conveniência. Sem ela, uma ameaça ao harness só passava no fiscal
apontando para um `CMP-*` arbitrário que por acaso existisse: era o caso de
`THREAT-HARNESS-ELEVATION`, cujas mitigações são a política de higiene de ambiente, o hook de bash
e um gate da suíte — nada disso pertencendo ao componente que ela declarava ameaçar. **Conformidade
por vacuidade dentro do fiscal que existe para impedi-la**, e ela passava verde sem que ninguém
tivesse errado nada de propósito.

O defeito só ficou visível num derivado, onde o conjunto de componentes esvazia e não sobra nome
arbitrário para apontar. Vale como lembrete do que a genericidade compra: o molde não expõe esta
classe de erro porque nele qualquer alvo resolve.

---

Fiscalizado por: `ci/validate_metadata.py::check_threat_model` (alvo e residual resolvem;
mitigação `local_path` existe); `ci/validate_metadata.py::check_dependency_inventory` (declarada
⇔ inventariada, nos dois sentidos); `harness/schemas/threat-model.schema.json` (mitigação com
`minItems: 1`; `residual_risk` obrigatório; STRIDE fechado; alvo em `CMP|IFC|UI|STAGE`);
`harness/schemas/dependencies.schema.json`; `.github/workflows/governance.yml`.
Declarado em: `security/threat-model.yaml`, `security/dependencies.yaml`,
`architecture/adr/index.yaml`, `harness/stages.yaml`.
Falha como: ameaça sem alvo ou residual resolvível, dependência declarada e não inventariada, ou
entrada morta no inventário ⇒ exit 1; metadado ilegível ⇒ exit 2.
