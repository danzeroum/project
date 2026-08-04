# Política: código sem metadado não existe

Todos os fiscais deste repositório verificavam uma direção só. `check_capabilities` pergunta se o
`source_path` declarado aponta para um arquivo real; `check_components` pergunta se o `tested_by`
existe; as asserções do ADR-005 perguntam se o import proibido apareceu. Nenhum perguntava a
inversa: **esse arquivo de código é reivindicado por algum metadado?**

Com uma direção só, um arquivo novo entra e passa. Não há erro, não há aviso, e o repositório
continua verde afirmando uma rastreabilidade capacidade → componente → código → teste que aquele
arquivo nunca teve. É o mesmo modo de falha do ADR-002 — a coisa que ninguém verifica dura para
sempre — só que do lado de fora do metadado.

## A regra

Todo arquivo sob as **raízes de código declaradas** pertence a `source_paths` de **exatamente um**
componente, ou a uma isenção justificada em `architecture/components.yaml:exemptions`.

E as três companheiras, que fecham o resto da mesma superfície:

| Check | Pergunta | Falha quando |
|---|---|---|
| `check_orphan_code` | esse código tem dono? | arquivo sem `CMP-*` nem isenção; ou com dois donos |
| `check_orphan_tests` | essa evidência é reivindicada? | teste fora de `tested_by`/`test_paths`/`validated_by` |
| `check_declared_dependencies` | o acoplamento real foi declarado? | import entre componentes fora de `depends_on` |
| `check_exposes` | o símbolo declarado existe? | `exposes` que o código não define |

## Dono ambíguo é dono nenhum

Dois componentes reivindicando o mesmo arquivo não é redundância inofensiva: quando esse arquivo
mudar, os dois times acharão que o outro revisou. A trava exige **exatamente um**.

## As raízes são declaradas, nunca convencionadas

`project.yaml:target.code_roots` e `target.test_roots` no derivado; as raízes do próprio molde
quando ele não governa alvo algum. O prefixo `src/` deixou de ser literal dentro do fiscal — não
por afrouxamento, mas porque cravar convenção no fiscal é a forma mais discreta de tornar o molde
específico de um alvo.

E raiz declarada que não existe é **exit 2**, não achado: um fiscal que percorre conjunto vazio
reporta verde, e verde por vacuidade é indistinguível de verde por cobertura.

## Ignorância declarada, nunca silêncio

O inventário é multi-linguagem por adapters registrados — acrescentar linguagem escreve um módulo
em `ci/adapters/`, não um `elif` no dispatcher. Três níveis:

- **semântico** (`python`): símbolos e arestas de import de verdade;
- **semântico parcial** (`typescript`): imports relativos e **alias de workspace**, resolvidos
  pelos `package.json` sob as raízes — não por `tsconfig:paths`, que um alvo real provou
  insuficiente. Declara que não resolve re-export em cadeia nem import dinâmico;
- **genérico** (o resto): resolve só pertencimento — que é o que a invariante precisa — e declara
  que não leu símbolos nem arestas.

Nenhum arquivo escapa, porque o genérico casa qualquer extensão. Um alvo em Go continua
respondendo "esse arquivo tem dono?" sem que ninguém tenha escrito um leitor de Go. O que se perde
são as arestas de dependência, e a perda **aparece no laudo**. É a diferença entre um fiscal que
não sabe e um fiscal que finge saber.

O TypeScript usa parser próprio, e não `dependency-cruiser`, deliberadamente: adotá-lo faria este
molde — Python puro — passar a exigir toolchain de Node para fiscalizar qualquer alvo, inclusive
alvos sem Node. Trocar isso por resolução de alias é uma decisão futura legítima; tomá-la em
silêncio, não.

## A conta fecha, ou o inventário é recusado

Todo especificador de import cai em exatamente um balde — **resolvido**, **externo** ou
**unresolved** — e o inventário é recusado (exit 2) quando
`resolvidos + externos + unresolved ≠ total`.

Isto não é zelo: foi medido. Num monorepo real, 84 arestas entre pacotes sumiam porque o adapter
resolvia só caminho relativo e descartava alias de workspace em silêncio. Ele cumpria *nunca
inventar aresta* e quebrava *declarar o que não leu* — e com um componente por pacote, aquelas 84
arestas **eram** o grafo de dependência: `check_declared_dependencies` validava `depends_on`
contra conjunto vazio e reportava verde.

A aritmética é a trava certa porque o modo de falha não é resolver errado, é **engolir**. Um teste
de caso pega o bug de hoje; a conta pega o próximo caminho de código que ler um import e não o
classificar.

## Por que import não declarado acusa e `depends_on` sobrando não

Import que existe e ninguém declarou é acoplamento que nenhuma decisão registrou — é achado.
`depends_on` sem import correspondente é só aviso: pode ser dependência legítima que o adapter não
enxerga (alias de monorepo, injeção em runtime). Reprovar aí criaria pressão para **apagar
declarações verdadeiras** só para o CI passar, que é exatamente o inverso do objetivo.

## Limite honesto

O fiscal verifica pertencimento sobre as raízes **declaradas**. Código fora delas não é órfão —
é território não declarado, e quem o declara é o reconhecimento do `/adotar` (ADR-008). A trava
aqui reprova raiz inexistente e arquivo sem dono; ela não descobre uma raiz que ninguém mencionou.

---

Fiscalizado por: `ci/validate_metadata.py::check_orphan_code` (pertencimento e isenção morta);
`ci/validate_metadata.py::check_orphan_tests`; `ci/validate_metadata.py::check_declared_dependencies`;
`ci/validate_metadata.py::check_exposes`; `ci/inventory_code.py` (inventário; raiz ausente ⇒ exit 2);
`harness/schemas/components.schema.json` (`exemptions` exige `justification`);
`.github/workflows/governance.yml` (passos negativos que provam a mordida).
Declarado em: `architecture/adr/index.yaml`, `architecture/components.yaml`, `project.yaml`.
Falha como: código, teste, dependência ou símbolo divergentes do declarado ⇒ exit 1; raiz
declarada ausente ou arquivo ilegível pelo adapter ⇒ exit 2.
