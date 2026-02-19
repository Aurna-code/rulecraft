# Rulecraft Contracts & Schemas SSOT — v0.1.0

- 문서 리비전: **ssot10**
- 작성일: 2026-01-26 (Asia/Seoul)
- 수정일: 2026-02-18 (Asia/Seoul)
- 패치:
  - TongGeometry(GTS) 메타데이터 — run.mode="tree" + RunLog.tree_search 추가
  - NN-FT(2601.14453) — FlowMapSnapshot.estimator(옵션) 추가
  - Categorical Flow Maps(2602.12233) — 범주형 정책/개입 분포를 few-step 추정기로 증류 + test-time guidance(옵션)
  - CL-bench(2602.03587) — CONTEXT_LEARNING violated_constraints + rubric-as-FGFC(unitization="rubric") + CLPack v1(RegressionTestSpec 템플릿) 추가
  - Memory Subsystem 계약(Phase 0/1) + intent/state 기반 RECALL(Phase 1) + Folding + Memory Actions(Phase 2) + PRAXIS(Phase 3, 조건부 전술 저장소)
  - hotfix09(원천) — InFi-Check FGFC(근거/오류타입/교정) 확장 계약 추가 + 관련 참조 갱신
  - hotfix12 — Patterning(데이터 개입) 오프라인 계약(PatterningPlan) 추가
  - hotfix12p1 — Validator/Router 무(無)모델 기본값 + 에스컬레이션 지표/트리거(관측 가능성) 추가
  - hotfix14 — ContextBlock + SieveGenPlan/SieveExample(옵션) 추가(Selective Context Injection 지원)
  - hotfix14p4 — Selective Context Injection 운영 최소 계약(context_select.version + 불변식/IDs-only) 정리
  - hotfix14p5 — Offline NavigatorGraph(오프라인) + HotPathBudget 상한 + early-exit(초기 디폴트)
  - Infomechanics(2601.15028) — 정보 보존/교환 관점의 Uncertainty Ledger + control_signals.infomech(옵션)
  - hotfix14p7(2601.22401) — IntentSatisfaction(meaningful correctness) + ProvenanceProbe(prior-art/출처) 신호 추가
  - hotfix14p8(base) — 운영 정합성 최소 계약(지표 의미/옵션 신호 범위/로그 불변식/튜닝 분리) 명문화
  - hotfix14p9 — Verification gap(UNKNOWN) 명문화 + Canary/rollback 프로토콜 구체화 + ContextBlock conflict 결정적 처리 규율
  - ENCOMPASS(2512.03571) — ExecutionPathSearch(EPS): branchpoint 기반 실행경로 탐색 메타데이터 + SearchNodeRecord(옵션) 추가
  - Reasoning Failures Survey(2602.06176) — RobustnessProbe(transform) + failure_taxonomy/robustness score_evidence 규범(옵션)
  - TKDE DataPrep Survey(2601.17058) — data_prep(정리/통합/보강)용 score_evidence 키 + violated_constraints 예시 + L3 하네스 연동 힌트
  - SMEL(2602.05182) — 모델 협업 출력→단일 모델 증류(오프라인) 메타데이터: RunLog.experiment.kind="collab_distill" + collab/distill(옵션)

> 이 파일은 Rulecraft v0.1.0의 **계약/스키마 단일 진실원천(SSOT)** 이다.
> Addendum(`RC_Addendum_rev17.md`)의 §3은 이 파일의 핵심 내용을 발췌/요약하며, 불일치가 생기면 **이 파일을 먼저 수정**한다.

---

## 3.0 공통 규칙

- 모든 레코드는 `schema_version`(문자열)을 **MUST** 포함한다.
- 모든 ID는 안정적 식별자이며, `*_id`는 **MUST** 전역 유일(충돌 없음)해야 한다.
- `verdict == PASS` 이더라도 `outcome == FAIL`이면 pass가 아니다(§5.1의 pass 정의를 따른다).
- `bucket_id`는 최소한 `impact_level × domain_tag × user_clarity`로 구성되는 문자열을 **SHOULD** 포함한다.

> 아래 형태는 구현 언어/스토리지와 무관한 “계약 형태”이다.
> 실제 JSON Schema로 분리할 경우 필드명·의미는 동일해야 한다.


---

## 5) 파생 정의(derived semantics) — 불변 규율

> 아래 항목은 “필드 추가”가 아니라, 여러 컴포넌트가 **같은 의미**로 해석해야 하는 전역 정의다.
> 문서 내 다른 곳에서 §5.1 등을 참조할 때는 이 정의를 따른다.

### 5.1 PASS 정의 (전역)
Rulecraft 전체에서 “PASS(pass=1)”는 **Validator의 verdict/outcome을 합성한 파생값**이다.

- `PASS := (verdict == "PASS") AND (outcome != "FAIL")`

의미:
- `outcome=="OK"`: 실행/근거로 **맞음이 확정**된 상태(가능하면 이 상태를 목표로).
- `outcome=="UNKNOWN"`: 검증 불가/불충분. `verdict`가 PASS이면 시스템은 “반증되지 않음”으로 PASS 처리하되,
  `should_escalate`/재검증/추가 근거 요구 등 **운영 정책으로 보강**할 수 있다.
- `outcome=="FAIL"`: 틀림이 확인된 상태. 이 경우 `verdict`가 PASS여도 pass는 0이다.

#### 5.1.1 CONFIRMED_PASS / SOFT_PASS (권장 파생값)

PASS 정의(§5.1)는 유지한다. 다만 운영/분석에서 outcome==UNKNOWN을 “검증 갭”으로 분리해 다루기 위해 아래 파생값을 권장한다.

- `CONFIRMED_PASS := (verdict == "PASS") AND (outcome == "OK")`
- `SOFT_PASS := (verdict == "PASS") AND (outcome == "UNKNOWN")`

권장 사용:
- (게이트) high impact(대외 발송/자동 액션/승격 입력)에서는 PASS만으로 충분하다고 가정하지 말고,
  `CONFIRMED_PASS`(또는 Addendum §5.3의 `p_ok_lb95`처럼 outcome==OK 기반 하한)을 우선 사용한다.
- (백로그 분류) `SOFT_PASS` 비율이 높은 버킷은 “쉬운 문제”가 아니라 “검증/근거 갭”일 수 있다.
  이 경우 정책 옵션은 (a) L3 하네스 확보, (b) probe/full에서 ProvenanceProbe 수행, (c) Intent-first 명확화/분해 템플릿 보강이다.
- (debias/선별) p_pass만으로 easy-case로 분류하지 말고, SSOT §5.4의 unknown_rate/insufficient_evidence_rate 같은 관측치를 함께 본다.

### 5.2 violated_constraints 키 규범 (집계 가능성)
`ValidationResult.violated_constraints`는 운영/회귀/FlowMap 집계를 위해 **자유 서술이 아니라 안정적인 키**로 기록한다.

- 권장 형태: `PREFIX:SUB:DETAIL` (문자열)
  - 예: `SCHEMA:ValidationResult`, `FORMAT:JSON_ONLY`, `TOOL:CALL_REQUIRED:web.search_query`, `POLICY:NO_NETWORK`
- 키의 의미/범위는 `Rulecraft_Validator_Spec_*`의 taxonomy와 일치해야 하며, 변경 시에는 **회귀/집계 코드도 같이 갱신**한다.

#### 5.2.1 (hotfix14p7) Intent/Provenance 신호 키(권장)

의도(meaningful correctness)와 선행/출처(provenance)는 **reason_codes를 늘리지 않고** `violated_constraints`로 표준화한다.
(세부 정의/운영 규율: ValidatorSpec §3.2.4/§3.2.5, Playbook §6.1)

- **INTENT** (산출물/형식/범위 충족)
  - `INTENT:NOT_SATISFIED`  # 요청 산출물/형식/범위를 충족하지 못함(기본 정책: K 확장보다 명확화/분해)
  - `INTENT:PARTIAL`        # 일부만 충족(누락 슬롯/단계 존재)
- **PROVENANCE** (선행/출처/인용)
  - `PROVENANCE:NOT_CHECKED`        # 선행/출처 체크를 수행하지 못함(핫패스 기본; 필요 시 probe/full에서만 수행)
  - `PROVENANCE:CITATION_MISSING`   # 인용/출처 요구가 있는데 누락
  - `PROVENANCE:LIKELY_KNOWN`       # novelty 주장 대비 상위 유사/선행이 강하게 감지됨(오염 방지 게이트)
  - `PROVENANCE:NEEDS_HUMAN_REVIEW` # 자동 판정 불가(리스크/중요도에 따라 HumanGate)

권장 증거 기록(SSOT 변경 없이 `score_evidence`로):
- `score_evidence.intent` / `score_evidence.provenance`

#### 5.2.2 (2602.06176) ROBUSTNESS 신호 키(권장, 옵션)

*Large Language Model Reasoning Failures* (TMLR 01/2026; arXiv:2602.06176)는 “사소한 변형에 의해 성능이 뒤집히는 숨은 취약성”을 **robustness issue**로 분리해 다룬다.
Rulecraft에서는 이를 “변형(transform) 기반 일관성 체크”로 운영에 옮길 수 있다.

아래 키들은 `reason_codes`를 늘리지 않고, `violated_constraints`로만 표준화하는 것을 권장한다.

- `ROBUSTNESS:VARIATION_SENSITIVE`
  - 의미: reword/순서변경/길이 변화/무관정보 삽입/관계 뒤집기 등 작은 변형에서 결과가 유의미하게 흔들림
  - 권장 처리: 기본은 `outcome=UNKNOWN` + should_escalate(High impact에서는 L3/EnvSuite로 확정 권장)
- `ROBUSTNESS:REVERSAL_CURSE`
  - 의미: “A is B”는 말하지만 “B is A” 류 역방향 질문에서 뒤집히거나 실패(=reversal curse 탐침 실패)

권장 증거 기록(SSOT 변경 없이 `score_evidence`로):
- `score_evidence.robustness` (probe_used/invariants/mismatch 등)


#### 5.2.3 (TKDE 2025; 2601.17058) DATA_PREP 신호 키(권장, 옵션)

LLM을 “데이터 준비(Data Preparation)”에 쓰면, 같은 실패가 반복해서 나온다:
- **로컬 문맥만 보고**(row/cell) 전체 제약(유니크/집계/상관/참조무결성)을 깨뜨리거나,
- **그럴듯한 값/설명**을 생성했지만 근거가 없거나(=hallucinated cleaning/enrichment),
- 매칭/클러스터링에서 **대칭성/추이성** 같은 전역 불변식이 깨진다.

아래 키들은 `reason_codes`를 늘리지 않고, `violated_constraints`로만 표준화하는 것을 권장한다.

- **GLOBAL / SCOPE**
  - `DATA_PREP:SCOPE:GLOBAL_VIEW_REQUIRED`
    - 의미: 데이터셋 전역 통계/제약(유니크, null rate, 분포, 집계 상관 등)이 필요한데, 로컬 컨텍스트만으로 처리하려 함
    - 권장 처리: L3(DataPrepHarness)로 승격해 전역 통계/제약을 계산해 주입하거나(RC_Validator_r08.md §3.3.3 DataPrepHarness), 작업을 분해/명확화

- **VALIDATION / CONSTRAINT**
  - `DATA_PREP:CONSTRAINT:VIOLATION`
    - 의미: 실행/검증(샌드박스/쿼리/룰체커)로 제약 위반이 확인됨
    - 예: `DATA_PREP:CONSTRAINT:VIOLATION:UNIQUE:email`, `...:NOT_NULL:order_id`, `...:REGEX:date_yyyy_mm_dd`

- **INTEGRATION INVARIANTS**
  - `DATA_PREP:INTEGRATION:SYMMETRY_BROKEN`
  - `DATA_PREP:INTEGRATION:TRANSITIVITY_BROKEN`

- **ENRICHMENT FAITHFULNESS**
  - `DATA_PREP:ENRICHMENT:UNSUPPORTED_CLAIM`
    - 의미: 프로파일/요약/메타데이터 생성 결과가 데이터 샘플/쿼리 결과/외부 근거로 지지되지 않음
    - 권장 처리: FGFC(세부 팩트체크) 또는 증거(샘플/쿼리) 요구

권장 증거 기록(SSOT 변경 없이 `score_evidence`로):
- `score_evidence.data_prep` (task/granularity/metrics/evidence 등; 아래 §ValidationResult.score_evidence 참고)

### 5.2.4 (CL-bench; 2602.03587) CONTEXT_LEARNING 신호 키(권장, 옵션)

CL-bench(2602.03587)은 “긴 컨텍스트 읽기/검색”을 넘어서, 컨텍스트에 담긴 **새 지식/규칙/절차/법칙**을 실제로 학습해 적용하는 능력을 측정한다.
Rulecraft 관점에서 이 실패는 대개 아래 3가지로 나타난다.

- (a) 컨텍스트를 읽었지만 답에 반영하지 못함(=일반론/환각으로 대체)
- (b) 컨텍스트가 사전지식(pre-training)과 충돌할 때 사전지식에 끌려가 컨텍스트를 위반
- (c) 답의 일부만 맞고, 루브릭(요건) 일부만 충족하는 “부분 성공”

아래 키들은 `reason_codes`를 늘리지 않고, `violated_constraints`로만 표준화하는 것을 권장한다.

- `CONTEXT_LEARNING:NOT_LEARNED`
  - 의미: 정답에 필요한 새 지식/정의/규칙이 컨텍스트에 있음에도, 답이 이를 사용하지 않음(또는 회피/환각으로 대체)
  - 권장 처리: 컨텍스트 전달 모드(`file_native`↔`prompt_embed`/`hybrid`) 조정 + ContextBlock(필요 조각) 재선정 + 근거 앵커 재탐색

- `CONTEXT_LEARNING:PRIOR_KNOWLEDGE_OVERRIDE`
  - 의미: 컨텍스트가 사전지식과 충돌(의도적으로 ‘수정된’ 규칙/사실)하는데, 모델이 사전지식을 따라 컨텍스트를 위반
  - 권장 처리: “컨텍스트 우선” ContextBlock 주입 + (가능하면) rubrics 기반 재검증(아래) + 오염 방지(메모리/룰 승격 금지)

- `CONTEXT_LEARNING:INCOMPLETE`
  - 의미: 루브릭/요건 중 일부만 충족(정답은 맞지만 절차/근거/예외/조건 누락 등)
  - 권장 처리: 루브릭을 FGFC로 unitize해 누락 항목을 `fgfc`에 남기고, counterexample_tests 생성(§RegressionTestSpec)

- `CONTEXT_LEARNING:TURN_DEPENDENCY_BROKEN`
  - 의미: 동일 컨텍스트 내 멀티턴(task i가 task i-1 결과에 의존)에서, 이전 합의/산출과 모순되거나 의존을 반영하지 못함
  - 권장 처리: WorkingSet에서 “context_digest/turn_state”를 분리 유지 + Folding 시 trace↔state 링크를 남겨 회귀 가능하게 한다

권장 증거 기록(SSOT 변경 없이 `score_evidence`로):
- `score_evidence.context_learning` (category/subcategory, rubric 통계, prior_override 등; §ValidationResult.score_evidence 참고)

(권장) CL-bench식 **verification rubrics**(요건 리스트)를 `FGFCReport`로 인코딩할 수 있다.
- `FGFCReport.unitization="rubric"`
- `SUPPORTED / REFUTED / NOT_ENOUGH_INFO`를 각각 `요건 충족 / 위반 / 불명`으로 해석한다.

#### CLPack v1 (Micro-Regression Pack: CONTEXT_LEARNING) — RegressionTestSpec로 “결정적” 회귀팩 만들기

CL-bench식 **verification rubrics(요건 리스트)** 는 그대로 두면 사람이 읽고 채점해야 해서 운영에 못 붙는다.
Rulecraft에서는 루브릭을 가능한 한 `RegressionTestSpec.assert` 로 환원해 **자동 채점 가능한 micro-regression** 으로 만든다.
이 묶음을 관례적으로 **CLPack v1**(= micro_regression_packs에 `CONTEXT_LEARNING` 추가)라고 부른다.

권장 루브릭→assert 매핑(가성비 순):
- **required token / 함수명 / 상수** → `regex_present`
- **forbidden token / 금지 우회 경로** → `regex_absent`
- **필수 파라미터/슬롯(구조적 요구)** → `json_schema`(키 존재/타입)
- **필수/금지 툴 정책** → `tool_called` / `tool_not_called`
- **멀티턴 의존 값(이전 turn 결과 재사용)** → `contains` 또는 `exact_match` (가능하면 L3 하네스로 값을 고정)

(권장) 실패 키 매핑 규칙(표준화 힌트):
- `regex_present/json_schema` 계열 critical 실패 → `CONTEXT_LEARNING:NOT_LEARNED`
- 비치명(설명/예외/절차) 누락 → `CONTEXT_LEARNING:INCOMPLETE`
- `regex_absent`가 *prior_conflict_expected* 컨텍스트에서 깨짐 → `CONTEXT_LEARNING:PRIOR_KNOWLEDGE_OVERRIDE`
- 멀티턴 의존 검사 실패 → `CONTEXT_LEARNING:TURN_DEPENDENCY_BROKEN`

권장 tags(집계/검색용):
- `pack:CONTEXT_LEARNING` + `cl:*` (예: `cl:doc_binding`, `cl:prior_conflict`, `cl:multiturn`, `cl:tool_policy`)

예시(템플릿; 실제 값은 각 컨텍스트/태스크에 맞게 치환):
```yaml
# (1) 문서 바인딩: 반드시 포함해야 하는 토큰/함수
- schema_version: "0.1.0"
  test_id: "clpack_v1.doc_required_token.<TOKEN>"
  test_type: "regression"
  severity: "critical"
  input_ref: "<input_ref>"
  assert:
    type: "regex_present"
    args: {pattern: "<REGEX>"}
  tags: ["pack:CONTEXT_LEARNING","cl:doc_binding"]
  expected: {must_pass: true, notes: "컨텍스트에 명시된 필수 토큰/함수 사용"}
  linked_rule_ids: ["<rule_id>"]

# (2) 사전지식 우회 금지: 금지 토큰/우회 경로가 나오면 실패
- schema_version: "0.1.0"
  test_id: "clpack_v1.forbidden_token.<TOKEN>"
  test_type: "regression"
  severity: "critical"
  input_ref: "<input_ref>"
  assert:
    type: "regex_absent"
    args: {pattern: "<REGEX>"}
  tags: ["pack:CONTEXT_LEARNING","cl:prior_conflict"]
  expected: {must_pass: true, notes: "컨텍스트와 충돌하는 사전지식/우회 경로 금지"}
  linked_rule_ids: ["<rule_id>"]

# (3) 구조적 바인딩: 필수 파라미터/슬롯이 출력에 존재해야 함
- schema_version: "0.1.0"
  test_id: "clpack_v1.required_params.<SCHEMA>"
  test_type: "regression"
  severity: "critical"
  input_ref: "<input_ref>"
  assert:
    type: "json_schema"
    args:
      schema:
        type: object
        required: ["<param_a>","<param_b>"]
        properties:
          <param_a>: {type: string}
          <param_b>: {type: string}
  tags: ["pack:CONTEXT_LEARNING","cl:param_binding"]
  expected: {must_pass: true, notes: "필수 파라미터(슬롯) 누락 방지"}
  linked_rule_ids: ["<rule_id>"]
```


### 5.3 bucket_id 구성(최소 권장)
`RunLog.bucket_id`는 최소한 아래 3축을 포함하는 문자열을 권장한다.

- `impact_level × domain_tag × user_clarity`

예(표준은 아님, 가독성 우선):
- `I3|coding|clarity_low`
- `I1|general|clarity_high`
- `I2|math|clarity_med`

### 5.4 Validator/Router “무(無)모델” 운영을 위한 파생 지표(derived observables)

Rulecraft는 기본적으로 Validator/Router를 **코드 기반**으로 운영한다.
따라서 “모델을 추가해야 하나?”는 주관이 아니라 **로그에서 계산되는 관측치**로 판단한다.

권장 파생 지표(집계는 RunLog + ValidationResult에서 계산):
- **unknown_rate**: `count(outcome=="UNKNOWN") / N`
- **exec_unavailable_rate**: `count(reason_codes contains one of {sandbox_denied,sandbox_timeout,exec_unavailable}) / N`
- **l1_violation_rate**: `count(violated_constraints != null) / N`  (형식/제약 위반 비율)
- **insufficient_evidence_rate**: `count(reason_codes contains "insufficient_evidence") / N`
- **intent_not_satisfied_rate**(옵션): `count(violated_constraints contains "INTENT:NOT_SATISFIED") / N`
- **provenance_not_checked_rate**(옵션): `count(violated_constraints contains "PROVENANCE:NOT_CHECKED") / N`
- **cluster_recurrence**: 윈도우 내 `failure_cluster_id` 재발 빈도(상위 K개)
- **overinject_rate**(옵션): `count(reason_codes contains "memory_overinject" or "praxis_tactic_overinject") / N`
- **context_unknown_rate**(옵션): `mean(len(RunLog.context_select.unknown_context_ids)>0)`  (context_select 로그가 있을 때만)
- **context_token_saved_mean**(옵션): `mean(RunLog.context_select.token_est.saved)`  (대략치; 비교/회귀용)
- **context_conflict_prune_rate**(옵션): `mean(len(conflict_pruned_context_ids) / max(len(candidate_context_ids),1))`


운영 해석(권장):
- `unknown_rate`가 높아도, 그 원인이 `exec_unavailable_rate`라면 “L2 붙이기”보다 **L3(하네스/샌드박스) 확보**가 우선이다.
- 반대로 `insufficient_evidence_rate`가 높고 L3로 확정이 불가능한 텍스트 태스크가 병목이면, 그때만 제한적으로 L2(저비용 grader)를 검토한다.


### 5.5 Infomechanics(2601.15028) 기반 Uncertainty Ledger (optional)

> 목적: “왜 스케일했는지/왜 멈췄는지”를 감(感)으로 말하지 말고, **불확실 감소(정보 이득) vs 비용**으로 로그에 남긴다.
> 논문 포인트는 단순하다: Bayesian update에서 **posterior surprisal 감소는 데이터로부터 얻은 정보와 정확히 균형**을 이룬다.
> Rulecraft에선 이를 “완전한 수학”으로 구현하려고 애쓰지 말고, **관측 가능한 프록시(Proxy)** 로 운영한다.

권장 로그 단위: `RunLog.control_signals.infomech` (아래 InfoMechanicsLedger)

핵심 수치(권장):
- **p_pass_prior / p_pass_post**: 후보(또는 최종 답)의 PASS 확률(추정치)
- **surprisal_bits := -log2(p_pass)**
- **info_gain_bits := surprisal_bits_prior - surprisal_bits_post**  (양수면 불확실 감소)
- **ig_per_cost := info_gain_bits / max(delta_cost, ε)**  (스케일링 ROI)

추정 프록시(현실적인 것만):
- `p_pass`는 (a) bucket의 경험적 pass_p_hat/EMA, (b) L1 위반(강한 음수), (c) L3 테스트 PASS/FAIL(강한 ±), (d) L2 score(약한 보정)으로 업데이트한다.
- **phi_proxy / mode_count_eff**: posterior의 “울퉁불퉁함(다중 모드)”을 직접 계산 못 하니, rollouts/top-m의 **표현 공간 다양도**로 대체한다.
  예: rollout summaries를 임베딩 후 클러스터링해서 `mode_count_eff := exp(H(cluster))` 같은 값으로 기록.

운영 해석(권장):
- `ig_per_cost`가 계속 낮아지면 “더 찾는 건 낭비” 쪽으로 기운다(스케일 중단/답 확정).
- `mode_count_eff`가 높으면(=해답 후보가 여러 모드로 갈라짐) DraftSummarizeCompose-lite/K-drafts/GTS 같은 **탐색 확장**이 정당화된다.
- `info_gain_bits`가 음수(불확실 증가)로 누적되면: 프롬프트/룰/메모리 주입이 충돌했을 가능성이 높다(`instruction_conflict`, `memory_conflict`류로 표기). 이때는 “더 세게 생각”이 아니라 **주입/제약/라우팅을 정리**하는 게 먼저다.

주의:
- 이 ledger는 “정답 증명”이 아니다. **운영 의사결정(should_escalate/stop, budget, 탐색 확장)** 의 근거를 남기는 용도다.
- 값의 절대 정확도보다 **일관성(같은 정책에서 비교 가능)** 이 더 중요하다.



---

---

## 4) Memory Subsystem 계약 (Phase 0/1/2)

Rulecraft의 “메모리”는 감성적인 회상이 아니라, **실행 기반 재사용/학습을 위한 데이터 계약**이다.
목표는 딱 4개:

1) 실행 기록을 구조화해(TraceBundle/RunLog) **다음 런의 품질/비용을 낮춘다**
2) 태스크 진행 중 컨텍스트를 WorkingSet으로 정리해 **현재 fold를 안정화**한다
3) 장기 재사용 단위(에피소드/전술)를 ReasoningBank로 모아 **전술적 지식 베이스**를 만든다
4) 즉시 재시드/프롬프트 prior 캐시를 ReuseBuffer로 유지해 **가성비 롤아웃**을 돕는다

### 4.1 저장소 역할(Phase 0)

- **RunLog / TraceBundle (저장소)**
  - RunLog: 런의 **요약 메타**(선택된 룰, validator 결과, 비용, rollout 선택 등)
  - TraceBundle: 런의 **상세 컨텍스트 캡슐**(주입/툴/출력/근거 참조). RunLog는 TraceBundle을 `run_id`로 조인한다.

- **WorkingSet (작업 메모리)**
  - “현재 task fold 전”: 지금 수행 중인 문제에서 필요한 중간 상태/결정/가정/제약을 모은다.
  - 원칙: *작게, 빠르게, 자주 갱신* (장기 기억 아님).

- **ReasoningBank (장기 메모리: 에피소드/전술)**
  - 에피소드: “무엇을 했고 왜 통했는지” 요약(TraceBundle ↔ RunLog ↔ 결과)
  - 전술: 재사용 가능한 패턴(전략적 절차/체크리스트/검증 루틴/실험 설계)

- **Rulebook (승격 룰)**
  - 장기 “규칙”은 RuleRecord로 승격/버전관리한다(=Rulebook은 RuleRecord의 저장소 역할).

- **ReuseBuffer (캐시: seed/prior + 조건부 전술)**
  - 롤아웃/탐색 재시드용 seed/prior 상태(Phase 2까지) + PRAXIS의 조건부 전술(Phase 3)을 함께 담는다.
  - seed/prior는 `ReuseStateRecord`(PUCT로 선택), 조건부 전술은 `ConditionalTacticRecord`(intent/state로 리콜)로 구분한다.

### 4.2 메모리 오퍼레이션(Phase 0)

모든 저장소에서 아래 오퍼레이션은 **동일 의미**로 해석돼야 한다.

- **WRITE**: 새 레코드 생성(또는 동일 `memory_id`에 대한 버전 증가)
- **PIN**: TTL/PRUNE 대상에서 제외(강한 보존)
- **MERGE**: 여러 레코드를 합쳐 상위 요약(예: 여러 TraceBundle → 에피소드)
- **PRUNE**: 품질/신선도/중복 기준으로 삭제(또는 축약)
- **RETIRE**: “삭제”가 아니라 **비활성화 상태로 보관**(재현성/감사를 위해)
- **RECALL(intent,state)**: 아래 §4.3/§4.4 규율에 따른 검색/리콜

### 4.3 intent_key / state_key (Phase 1 핵심)

`bucket_id`가 “큰 바구니”라면, Phase 1의 핵심은 **리콜 오차를 줄이는 2중 키**다.

- **intent_key (안정)**: “무슨 종류의 일을 하려는가”
  - 예: `(domain_tag, task_family, required_tools, output_format, constraint_profile)`를 기반으로 만든 문자열/해시
- **state_key (휘발)**: “지금 어떤 실행 상태인가”
  - 예: `(run.mode, budget_tier, policy_profile, tool_availability, validator_profile, sandbox_flags)` 등

원칙:
- intent_key는 **재사용 가능성**을 가르고, state_key는 **호환성(실행 가능성)** 을 가른다.
- 둘 다 없는 경우 Phase 1 리콜은 “의미 유사도만”으로 퇴행(fallback)해도 된다(하지만 성능은 당연히 떨어진다).

### 4.4 RECALL 규율: STITCH-style filter → rerank (Phase 1)

RECALL은 “검색”이 아니라 “재사용 후보를 안전하게 좁히는 의사결정”이다.

1) **Candidate Gather** (소스별 top-k’):
   `ReasoningBank`, `Rulebook`, `ReuseBuffer`(tactic_entries, Phase 3), 필요 시 `TraceBundle`(최근/핀된 것 우선)
   - seed/prior 재시드는 RECALL이 아니라 `reuse_select`(PUCT) 경로로 분리한다.

2) **Filter (호환성 컷)**:
   - bucket_id/intent_key가 **명백히 불일치**하면 제거
   - state_key 호환성(툴/모드/정책/제약)이 깨지면 제거
   - (옵션) `PASS` 이력이 매우 낮거나 `RETIRE`된 항목은 기본 제외

3) **Rerank (가중 점수)**:
   `S = w_sem*sim(query, summary) + w_int*sim(intent, mem_intent) + w_state*compat(state, mem_state) + w_qual*quality(mem)`
   - quality(mem): pass_p_hat, cost 효율, recency, pinned bonus 등

4) **Return (MemoryHint)**:
   - top-m을 `MemoryRecallResponse.items[]`로 반환(요약/이유/trace 참조 포함)
   - 실제로 사용한 항목은 RunLog의 `memory_recall.used_ids`에 기록한다(관측 가능성).

#### 4.4.1 주입 예산(가벼운 메모리 기본값)

RECALL 산출물은 “좋은 글”이 아니라 **짧은 주입 단위**다. Orchestrator는 주입 예산을 **MUST** 강제한다(단위는 tokens 또는 chars 중 하나로 통일).

권장 기본값(Policy로 조정 가능):
- `MemoryHint.summary`: **≤ 120 tokens** (또는 ≤ 600 chars)
- `ConditionalTacticRecord.injection.content`: **≤ 160 tokens** (또는 ≤ 800 chars)
- 한 run에서 (룰 제외) **메모리 주입 총합 ≤ 256 tokens**

상한 초과 시:
- 내용은 더 압축(compaction)하거나 `payload_ref`로 외부화하고, Orchestrator는 초과분을 **잘라서 주입**한다.
- 장문 주입으로 컨텍스트가 오염되면, 그 순간부터 메모리는 “도움”이 아니라 “노이즈”다(인간과 LLM 모두에게).


### 4.5 Folding 규율 (Phase 2)

Folding은 “현재 task의 진행 상태(WorkingSet) + 실행 흔적(TraceBundle/RunLog) + 검증 신호(ValidationResult)”를
**재사용 가능한 단위(ReasoningBank/ReuseBuffer)로 접어 넣는 과정**이다.

원칙:
- Folding은 **요약(summarize)** 이 아니라 **재사용 단위 생성(distill-for-reuse)** 이다.
- Folding 결과는 “자동 승격”이 아니라 **후보 생성 + 관측 가능 로그**로 남겨야 한다.

권장 트리거(trigger.kind):
- `end_of_run` (기본)
- `ws_overflow` (WorkingSet 과대)
- `fail_cluster` (유사한 violated_constraints/reason_codes 반복)
- `phase_shift` (probe→full, mode 전환 등)
- `manual` (운영자/테스트 하네스 강제)

Folding 산출물:
- `FoldResult` (무엇을 접었고 무엇을 생성했는지)
- (옵션) `MemoryActionPlan` (어떤 메모리 오퍼레이션을 실행할지)

### 4.6 Memory Actions: Plan → Apply → Record (Phase 2)

Phase 0/1에서 정의한 메모리 오퍼레이션(WRITE/PIN/MERGE/PRUNE/RETIRE)은 Phase 2에서 **자동 실행 가능 형태**가 된다.

- Planner는 `MemoryActionPlan`을 생성한다(“무엇을, 어디에, 왜”).
- Executor는 Plan을 적용하고 `MemoryActionRecord`로 결과를 남긴다.

안전장치(필수):
- **Rulebook 자동 승격 금지**: Phase 2는 Rulebook에 “draft/temporary 후보”를 만들 수는 있어도,
  `status=active` 승격은 **tests/게이트를 통과한 별도 루프**에서만 수행한다.
- **PRUNE는 PIN/보존 대상 제외**: `status=pinned` 또는 최소 TTL 보호 대상은 PRUNE하지 않는다.
- 기본은 **RETIRE 우선**(재현성/감사). PRUNE은 저장소 부하/중복이 명확할 때만 제한적으로 사용한다.
- 모든 적용 결과는 RunLog에 연결되어야 한다(관측 가능성).

### 4.7 RunLog 확장: memory_fold / memory_actions (Phase 2)

Phase 2의 Folding/Actions는 “오프라인 집계(FlowMap/회귀/정책 개선)”를 위해 반드시 로그로 남겨야 한다.

- RunLog.memory_fold: FoldResult 연결 + 산출물(ReasoningBank/ReuseBuffer 후보) 요약
- RunLog.memory_actions: Plan/Record 연결(적용 결과, 실패 원인 포함)


---


### 4.8 PRAXIS: 조건부 전술 저장소로의 확장 (Phase 3)

Phase 3의 목적은 ReuseBuffer를 단순한 seed/prior 캐시에서 끝내지 않고, **“조건부 전술(conditional tactics)”** 을 담는 재사용 저장소로 확장하는 것이다.

- **ConditionalTacticRecord**는 “언제(조건) + 무엇(짧은 전술) + 왜(근거/효율)”을 담는다.
- 저장 위치는 ReuseBuffer 내부의 `tactic_entries`이며, seed/prior(`seed_entries`)와 **혼합하지 않는다**.
- 사용 경로:
  - (리콜) Phase 1 `RECALL(intent,state)`에서 `ReuseBuffer`(tactic_entries) 소스로 후보를 모아 filter→rerank 후 top-m을 `MemoryHint`로 반환한다.
  - (갱신) Phase 2의 Folding/Actions가 끝날 때, `MemoryActionPlan`에 따라 `WRITE/MERGE/RETIRE/PIN`으로 전술을 기록/갱신한다.
- 안전 규율(필수):
  - Conditional tactics는 **룰이 아니다**. Rulebook의 `active` 승격과 동치로 취급하면 안 된다.
  - 주입은 “힌트/체크리스트/짧은 절차” 수준으로 제한한다(장문 금지, 과주입 금지).
  - 실패/충돌 시에는 `RETIRE`를 우선하고, `PRUNE`은 저장소 부하가 명확할 때만 제한적으로 수행한다.


## 스키마 목록


### RuleRecord
```yaml
RuleRecord:
  schema_version: "0.1.0"
  rule_id: string               # MUST
  version: string               # MUST (예: semver 또는 내부 버전)
  type: "StrategyRule" | "GuardrailRule"     # MUST
  status: "temporary" | "active" | "retired" # MUST

  title: string                 # SHOULD
  body: string                  # MUST (룰의 실제 텍스트/절차/금지사항)

  applicability:                # MUST
    domain_tag: string          # SHOULD
    task_family: string         # SHOULD
    predicates:                 # MAY (간단 규칙식 / feature predicate)
      - string
    bucket_ids:                # MAY (명시적 버킷 타겟)
      - string

  priority:                     # SHOULD (주입/적용 순서)
    guardrail_first: bool       # MUST (GuardrailRule이면 true 권장)
    rank: int                   # MAY

  evidence:                     # MUST (근거 링크)
    run_ids: [string]         # SHOULD
    validator_ids: [string]      # MAY
    regression_ids: [string]    # MAY

  tests:                        # MUST
    regression_tests: [string]        # MUST (없으면 empty)
    counterexample_tests: [string]    # MUST (없으면 empty)

  metrics:                      # MUST
    utility_q_ema: float               # SHOULD
    pass_p_hat: float | null           # SHOULD
    pass_p_lb95: float | null          # SHOULD
    pass_p_K: int | null               # SHOULD
    pass_p_bucket:                    # MAY
      "<bucket_id>":
        p_hat: float
        p_lb95: float
        K: int


    pass_p_bucket_delta:               # MAY (룰 적용 전후 변화 추정; replay/canary에서 갱신)
      "<bucket_id>":
        delta_p_hat: float|null
        delta_p_lb95: float|null
        delta_K: int|null
  lifecycle:                    # MAY
    created_at: string
    updated_at: string
    last_used_at: string
    retire_candidate: bool
```


### RuleSelectRequest/Response
```yaml
RuleSelectRequest:
  schema_version: "0.1.0"
  request_id: string        # MUST
  input_ref: string             # MUST (입력/태스크 식별자 또는 해시)
  bucket_id: string        # SHOULD
  context:
    impact_level: "low"|"med"|"high"   # SHOULD
    domain_tag: string                   # SHOULD
    user_clarity: "low"|"med"|"high"  # SHOULD
  constraints:
    max_rules: int          # MUST
    allow_types: ["StrategyRule","GuardrailRule"]  # MUST
    prompt_profile: string  # SHOULD

RuleSelectResponse:
  schema_version: "0.1.0"
  request_id: string        # MUST
  applied_rules:           # MUST
    - rule_id: string
      version: string
      type: "StrategyRule"|"GuardrailRule"
      injection_mode: "prepend"|"inline"|"system_guard"  # MUST
      score: float          # SHOULD
      reasons: [string]     # MAY
  exploration:
    used_debias: bool       # SHOULD
    debias_weight: float|null
    used_novelty: bool|null     # MAY (mode collapse 방지용 탐색 신호)
    novelty_weight: float|null  # MAY (보상/선택에서 novelty 가중치)
    diversity_score: float|null # MAY (집단 내 유사도↓일수록↑ 같은 얕은 지표)
```


### ValidationResult
```yaml
ValidationResult:
  schema_version: "0.1.0"
  validator_id: string       # MUST
  verdict: "PASS"|"FAIL"|"PARTIAL"   # MUST
  outcome: "OK"|"FAIL"|"UNKNOWN"      # MUST
  score: float|null             # SHOULD (0~1, 선별/스케일링에 쓰는 주 점수)
  score_method: "yes_logit"|"pairwise_rank"|"rule_check"|"hybrid"|null  # MAY
  score_evidence: object|null   # MAY (예: {yes_logit:float, confidence:float, applicability:{...}, intent:{...}, provenance:{...}, robustness:{...}, failure_taxonomy:{...}})
  failure_cluster_id: string|null       # MAY
  notes: string|null        # MAY
  reason_codes: [string]|null          # SHOULD (FAIL/PARTIAL 시 최소 1개 권장)
  violated_constraints: [string]|null  # MAY (정적 규칙/제약 위반 목록)
  fgfc: object|null   # MAY (Fine-Grained Fact Checking payload; see FGFCReport)
  scores:                   # MAY
    holdout_score: float|null
    safety_score: float|null
#### ValidationResult.score_evidence (권장 서브키; SSOT 호환)

`score_evidence`는 스키마 확장을 최소화하기 위해 “가변 payload”로 둔다.
단, 운영/회귀/패턴링에서 자주 쓰이는 신호는 **키 이름을 고정**해 두는 편이 좋다.

- `score_evidence.robustness` (옵션): 작은 변형(transform) 입력에서의 일관성/민감도 기록
  - 예: 어떤 변형에서 어떤 불변식이 깨졌는지(=숨은 취약성)
- `score_evidence.failure_taxonomy` (옵션): 실패를 “분류 힌트”로 라벨링
  - 출처: *Large Language Model Reasoning Failures* (TMLR 01/2026; arXiv:2602.06176)에서 제안한 2축(ReasoningType × FailureType)

- `score_evidence.data_prep` (옵션): 데이터 준비(cleaning/integration/enrichment)용 평가 신호/메트릭/근거
  - 출처: *Can LLMs Clean Up Your Mess?* (TKDE 2025; arXiv:2601.17058)에서 정리한 granularity/메트릭 관점

- `score_evidence.context_learning` (옵션): **컨텍스트 학습(Context Learning)** 평가 신호/루브릭 통계/사전지식 간섭 여부
  - 출처: *CL-bench: A Benchmark for Context Learning* (arXiv:2602.03587)

권장 형태(예시; **필드 추가여도 SSOT 위반 아님**):
```yaml
score_evidence:
  robustness:
    probe_used: ["transform:reword", "transform:reverse_relation"]
    invariants: ["final_answer", "json_schema", "tool_plan"]
    mismatch: true
    mismatch_on: ["final_answer"]
  failure_taxonomy:
    reasoning_type: "informal"|"formal"|"embodied"|null
    failure_type: "fundamental"|"limitation"|"robustness"|null
    category: string|null   # 예: "cognitive_bias", "reversal_curse", "compositional_reasoning"
  data_prep:
    task: "cleaning"|"integration"|"enrichment"|null
    subtask: string|null          # 예: standardization / error_processing / imputation / entity_matching / schema_matching / annotation / profiling
    granularity: "record"|"schema"|"object"|null
    metrics: object|null          # 예: {correctness:{f1:..}, ranking:{mrr:..}, semantic_preservation:{rouge:..}}
    evidence: object|null         # 예: {sample_refs:[...], query_refs:[...], external_refs:[...]}
  context_learning:
    category: "domain_knowledge"|"rule_system"|"procedure"|"empirical_discovery"|null
    subcategory: string|null
    rubrics_total: int|null
    rubrics_passed: int|null
    rubrics_failed: int|null
    prior_override: bool|null      # 컨텍스트-사전지식 충돌 시 사전지식으로 덮어쓴 흔적
```

```


### FGFCReport (Fine-Grained Fact Checking) — optional extension

> 목적: Validator가 단순 PASS/FAIL을 넘어서, **어디가 어떻게 틀렸는지(세부 오류 타입) + 근거 + 교정안**을 구조화해 반환할 수 있게 한다.
> 기본 아이디어는 InFi-Check(2601.06666)의 “fine-grained fact-check” 출력 형태와 호환된다.

```yaml
FGFCReport:
  schema_version: "0.1.0"
  mode: "infi_check_v1"            # 고정 문자열(호환성 키)
  unitization: "sentence"|"atomic_claim"|"rubric"  # 권장: sentence부터 시작
  units:
    - unit_id: string              # 예: "s0", "s1" (candidate 내부 단위)
      text: string
      verdict: "SUPPORTED"|"REFUTED"|"NOT_ENOUGH_INFO"
      error_type: "PredE"|"EntE"|"CircE"|"CorefE"|"LinkE"|"OutE"|null  # REFUTED 시 권장
      evidence:
        - source: "input_ref"|"artifact"|"tool"
          ref: string              # 예: "input_ref:doc#p3" / "artifact:testlog#L120-L140"
          quote: string|null       # 25단어 이내 권장(집계/검토용)
      justification: string|null   # 짧게(요약형)
      correction: string|null      # 교정문(가능하면 최소 수정)
  overall:                          # 단순 집계(옵션)
    supported: int|null
    refuted: int|null
    nei: int|null
  metrics:                          # 평가/오프라인에서 주로 사용(옵션)
    sar: float|null                 # 판정-근거 정합성(Strict/Normal 비율 등)
    strict_acc: float|null          # 단위+타입까지 맞춘 정확도(벤치마크용)
```

권장 매핑(집계용):
- `error_type → reason_codes` (예시)
  - PredE → `fact_predicate_mismatch`
  - EntE  → `fact_entity_mismatch`
  - CircE → `fact_circumstance_mismatch`
  - CorefE→ `fact_coreference_mismatch`
  - LinkE → `fact_discourse_link_mismatch`
  - OutE  → `fact_extrinsic_claim`



- `search/prover → reason_codes` (예시)
  - Search budget 소진 → `search_budget_exhausted`
  - 외부 prover/solver 불완전(unknown/incomplete) → `prover_incomplete`
  - prover가 증명을 찾지 못함(시간/깊이 내) → `proof_not_found`

### RunLog
```yaml
RunLog:
  schema_version: "0.1.0"
  run_id: string          # MUST
  input_ref: string             # MUST
  bucket_id: string        # SHOULD

  run_tags: [string]|null     # MAY (예: planner-heavy, tool-heavy, validator-heavy)
  control_signals:              # MAY (FlowMap/Policy 입력 투명화)
    risk_score: float|null
    opp_score: float|null
    efficiency: float|null
    infomech: InfoMechanicsLedger|null   # MAY (Infomechanics: 정보이득/비용 + 지형 프록시)
    budget_tier: "hot"|"probe"|"full"|null      # MAY (BudgetController가 선택한 티어)
    should_escalate: bool|null                 # MAY
    repair_attempted: bool|null                # MAY
    repair_succeeded: bool|null                # MAY
    adapter_calls: int|null                    # MAY
    budget_caps:                               # MAY (적용된 상한; 비교/회귀용)
      max_tokens_total: int|null               # MAY (tokens_in+out 총상한; 추정치 허용)
      max_tool_calls: int|null                 # MAY
      max_latency_ms: int|null                 # MAY
    early_exit: bool|null                      # MAY (중간 티어에서 종료했는지)
    exit_stage: string|null                    # MAY (예: "l1", "l1_repair")
    exit_reason: string|null                   # MAY (예: "confident_pass", "deadzone", "budget_cap", "clarify")

  applied_rules:              # MUST (RuleSelectResponse의 일부 미러)
    - rule_id: string
      version: string
      type: string

  # (옵션) 실행-기반 평가/탐색 컨텍스트(Execution-grounded loop)
  experiment:                  # MAY
    kind: "policy_search"|"execution_eval"|"rule_evolve"|"scaling_law"|"collab_distill"|null
    harness_id: string|null
    idea_id: string|null
    search_epoch: int|null
    population_id: string|null
    parent_ids: [string]|null
    mutation_ops: [string]|null
    exec_ok: bool|null
    exec_failure_class: string|null

    # (옵션) 모델 협업/증류(오프라인) 메타데이터 — SMEL(2602.05182) 스타일
    collab:                     # MAY
      strategy: string|null      # SHOULD (예: "multi_agent_debate"|"api_router"|"logit_fusion"|"weight_merge")
      model_ids: [string]|null   # SHOULD (참여 모델/어댑터 ID)
      rounds: int|null           # MAY (debate/iter count)
      summarizer_id: string|null # MAY (최종 합성/요약 담당 모델/어댑터)

    distill:                    # MAY
      method: string|null        # SHOULD (예: "supervised_kd"|"multi_student_kd"|"on_policy_kd")
      student_model_id: string|null  # MAY (주 대상 1개일 때)
      dataset_id: string|null    # MAY (예: "collab_distill_d04")
      mix:                      # MAY (multi-student KD 혼합 비율; 합 1.0 권장)
        teacher: float|null      # MAY (collab output)
        best_student: float|null # MAY (strongest student)
        self: float|null         # MAY (self output)

    reward:                    # MAY
      total: float|null
      pass: float|null
      cost: float|null
      diversity: float|null
      consistency: float|null

  # (옵션) ReuseBuffer에서 seed를 선택해 롤아웃/탐색을 '재시드'한 경우의 선택 메타데이터
  reuse_select:                        # MAY
    enabled: bool|null                 # MAY
    policy: string|null                # MAY (예: "puct_maxq_rankprior_v1")
    selected_state_id: string|null     # MAY
    selected_score: float|null         # MAY (PUCT score)
    puct:                              # MAY
      c: float|null                    # MAY (exploration constant)
      Q_method: "max_reward"|"mean_reward"|null   # MAY
      P_method: "rank_prior"|"uniform"|null       # MAY
      Q: float|null                    # MAY (selected state's Q)
      P: float|null                    # MAY (selected state's P)
      T_total: int|null                # MAY (총 선택 횟수)
      N: int|null                      # MAY (selected state's 선택 횟수)


  # (옵션) Selective Context Injection: ContextBlock 선택/주입 메타데이터 (선택적 주입의 '관측' 계약)
  context_select:                         # MAY
    enabled: bool|null               # MAY
    version: string|null              # MAY (context_select contract version, e.g. "context_select_v1")
    policy: string|null              # MAY (예: "l0_only", "l0_then_l2_applicability")
    l0_top_n: int|null               # MAY (L0 candidate cap)
    candidate_context_ids: [string]|null  # MAY (L0 통과 후보)
    applicable_context_ids: [string]|null # MAY (L0/L2 판정 적용)
    rejected_context_ids: [string]|null   # MAY
    unknown_context_ids: [string]|null    # MAY (애매하면 남김)
    conflict_pruned_context_ids: [string]|null  # MAY (상충/중복 제거)
    injected_context_ids: [string]|null   # MAY (실제 프롬프트에 넣은 ContextBlock)
    token_est:                       # MAY (대략치; 비교/회귀용)
      candidates: int|null           # MAY (candidate 전체를 넣었을 때 추정 토큰)
      injected: int|null             # MAY (실제 주입 추정 토큰)
      saved: int|null                # MAY (candidates - injected)
    notes: string|null               # MAY



# (옵션) Context Engineering: 모델/런타임에 따른 컨텍스트 전달/탐색 관측 (arXiv:2602.05447)
context_eng:                       # MAY
  enabled: bool|null               # MAY
  version: string|null             # SHOULD (e.g. "context_eng_v1"); enabled=true면 사실상 MUST로 운용 권장
  access_mode: "file_native"|"prompt_embed"|"hybrid"|null   # MAY
  format: "yaml"|"md"|"json"|"toon"|"custom"|null           # MAY
  navigator_used: bool|null        # MAY
  navigator_profile: string|null     # MAY (예: "nav_default_v1")
  navigator_source: "static"|"offline_graph"|null   # MAY
  unknown_fields: [string]|null       # MAY (스키마에 없는 context_eng 하위 키 목록; FAIL 대신 관측)
  domain_partition:                # MAY
    enabled: bool|null             # MAY
    domain: string|null            # MAY
    shard: string|null             # MAY
  grep_tax:                        # MAY (검색 실패/반복 오버헤드 관측)
    attempts: int|null             # MAY
    failed: int|null               # MAY
    retrieval_tokens: int|null     # MAY (가능하면)
    overhead_tokens_est: int|null  # MAY (추정치; 비교/회귀용)
  notes: string|null               # MAY

  # (옵션) Search 메타데이터: ExecutionPathSearch(EPS) / Guided Tree Search(GTS)
  # - EPS(ENCOMPASS): 실행 파이프라인의 branchpoint에서 로컬 재샘플/빔서치
  # - GTS(TongGeometry): 상태-행동(state/action) 트리 서치(형식-검증 가능한 도메인)
  tree_search:                         # MAY
    enabled: bool|null                 # MAY

    # 알고리즘/프로파일
    algo: string|null                  # MAY (예: "eps_local_resample_v1","eps_beam_v1","puct_guided_tree_v1")
    kind: "execution_path"|"state_action"|null   # MAY
    profile_id: string|null            # MAY (search config id; 문서 밖 config로 분리 권장)
    search_id: string|null             # MAY (SearchNodeRecord.search_id와 조인)

    # 예산/형태(요약)
    branching_default: int|null        # MAY (branchpoint 기본 분기 수)
    beam_width: int|null               # MAY (beam일 때)
    resample_policy: string|null       # MAY (예: "protect_on_exception_v1")
    resample_on: [string]|null         # MAY (예: ["schema_invalid","tool_exception","parse_fail"])

    # 집계 카운터(관측용)
    node_expanded: int|null            # MAY
    depth_max: int|null                # MAY
    frontier_max: int|null             # MAY
    resampled_n: int|null              # MAY
    killed_n: int|null                 # MAY
    kill_reasons: object|null          # MAY (stable_key -> count)

    # 베스트 노드/스코어(요약)
    best_node_id: string|null          # MAY (SearchNodeRecord.node_id)
    best_node_ref: string|null         # MAY (예: run_id:step#k 또는 외부 저장소 ref)
    best_score: float|null             # MAY
    best_verifier:                     # MAY
      verdict: string|null
      outcome: string|null
      score: float|null

    node_store_ref: string|null        # MAY (SearchNodeRecord 저장소 ref)
    notes: string|null                 # MAY



  # (옵션) Phase3 PRAXIS 조건부 전술 리콜/사용 메타데이터
  praxis:                              # MAY
    enabled: bool|null                 # MAY
    policy: string|null                # MAY (예: "praxis_conditional_tactics_v1")
    retrieved_tactic_ids: [string]|null # MAY (top-k 후보)
    used_tactic_ids: [string]|null      # MAY (실제로 주입/참조한 전술)
    top_scores: [float]|null            # MAY (retrieved와 동일 순서)
    notes: string|null                  # MAY (failover, override 등)

  # (옵션) Phase1 메모리 RECALL 메타데이터 (intent/state 기반)
  memory_recall:                      # MAY
    enabled: bool|null                # MAY
    method: string|null               # MAY (예: "intent_state_recall_v1")
    intent_key: string|null           # MAY
    state_key: string|null            # MAY
    sources: [string]|null            # MAY (예: ["ReasoningBank","Rulebook","ReuseBuffer","TraceBundle"])
    retrieved_ids: [string]|null      # MAY (top-k 후보)
    used_ids: [string]|null           # MAY (실제로 주입/참조한 항목)
    top_scores: [float]|null          # MAY (retrieved_ids와 동일 순서)
    notes: string|null                # MAY (failover, override 등)

  # (옵션) Phase2 Folding + Memory Actions 메타데이터
  memory_fold:                        # MAY
    enabled: bool|null                # MAY
    fold_id: string|null              # MAY (FoldResult.fold_id)
    trigger_kind: string|null         # MAY (예: "end_of_run", "ws_overflow")
    ws_id: string|null                # MAY (WorkingSet.current_ws_id 등)
    produced_reasoning_ids: [string]|null   # MAY (ReasoningMemoryRecord ids)
    produced_rule_draft_ids: [string]|null  # MAY (DistillDraft.draft_id 등)
    produced_reuse_state_ids: [string]|null # MAY (ReuseStateRecord ids)
    action_plan_id: string|null       # MAY (MemoryActionPlan.plan_id)
    action_record_ids: [string]|null  # MAY (MemoryActionRecord.op_id 리스트)
    notes: string|null                # MAY

  memory_actions:                     # MAY (Phase2)
    enabled: bool|null                # MAY
    plan_id: string|null              # MAY
    op_ids: [string]|null             # MAY
    notes: string|null                # MAY


  run:
    mode: "main"|"sot"|"matts"|"kroll"|"compose"|"tree"    # MUST
    cfg:                               # MAY (jitter, seed 등)
      seed_prompt: string|null
      tool_order: string|null
      temperature: float|null
      plan_style: string|null
      self_refine_steps: int|null

  sandbox:                              # MAY (LLM-in-Sandbox)
    enabled: bool|null
    image_id: string|null               # 예: docker image digest/tag
    network: "off"|"allowlist"|"on"|null
    allowlist: [string]|null
    turns: int|null                     # sandbox interaction turns
    actions_n: int|null                 # tool actions (bash/edit)
    files_read_n: int|null
    files_written_n: int|null
    external_fetch_n: int|null          # network fetch count (if any)
    exec_fail_n: int|null
    traces_ref: [string]|null           # SandboxActionTrace ids (separate store)

  sot_profile: string|null           # MAY (예: "sot_mini_v1")
  sot_max_turns: int|null            # MAY (예: 2~3)

  outputs:
    output_ref: string|null                   # SHOULD (결과 참조)
    draft_summary: RolloutSummary|null # SHOULD (kroll/matts에서 요약 메시지)
    self_review_signals: object|null             # SHOULD (sot에서 대화 행동 신호: qa/shift/conflict/reconcile 등)
    compose_inputs:                        # MAY (compose에서 사용한 메시지 참조)
      used_run_ids: [string]|null
      used_summary_ids: [string]|null

  validator:                             # MUST
    validator_id: string
    verdict: string
    outcome: string

  cost:                                 # SHOULD
    latency_ms: int|null
    tokens_in: int|null
    tokens_out: int|null
    tool_calls: int|null

  draft_select:                        # MAY (K-drafts 결과 선별 메타; 요약 공간 TTS)
    rollouts_n: int|null                 # MAY (생성된 rollout 수)
    top_m: int|null                      # MAY (compose 입력으로 선택된 요약 수)
    selection_method: string|null        # MAY (예: "score+diversity")
    selected_summary_ids: [string]|null  # MAY
    diversity_score: float|null          # MAY (선별된 집합 기준)

  repr:                                  # MAY (Representation Space 캐시 참조)
    encoder_id: string|null
    dim: int|null
    x_vec_id: string|null
    y0_vec_id: string|null
    summary_vec_ids: [string]|null
```



### TraceBundle
```yaml
TraceBundle:
  schema_version: "0.1.0"
  run_id: string                 # MUST (RunLog.run_id와 조인)
  created_at: string               # MUST (ISO8601)

  bucket_id: string|null          # SHOULD (RunLog.bucket_id와 일치 권장)
  intent_key: string|null          # MAY
  state_key: string|null           # MAY

  # 저장은 "참조(ref)" 중심. 원본은 별도 스토리지(파일/DB/오브젝트)에 둘 수 있다.
  refs:
    input_ref: string|null             # MAY (입력 원문/요약 참조)
    injection_ref: string|null     # MAY (주입된 룰/메모리 스니펫 참조)
    tool_trace_refs: [string]|null # MAY (SandboxActionTrace ids 등)
    output_ref: string|null             # MAY (출력 원문/요약 참조)
    validator_ref: string|null      # MAY (Validator 상세 로그 참조)

  # RECALL/주입에 실제로 쓰인 항목 기록(관측 가능성)
  used_memory_ids: [string]|null   # MAY
  used_rule_ids: [string]|null     # MAY

  # 민감정보/대형텍스트는 기본적으로 여기에 넣지 말고 refs로 분리한다.
  # 운영 규율(권장): RunLog/TraceBundle에 원문 PII/secret(키/토큰/개인식별자)를 직접 저장하는 것은 MUST NOT.
  # refs가 가리키는 원본 저장소에도 동일한 리다액션/접근제어/보존기간(TTL) 정책을 적용한다.
  notes: string|null               # MAY
```


### FoldResult
```yaml
FoldResult:
  schema_version: "0.1.0"
  fold_id: string                 # MUST
  created_at: string              # MUST (ISO8601)

  trigger:                        # MUST
    kind: "end_of_run"|"phase_shift"|"ws_overflow"|"budget_hit"|"fail_cluster"|"manual"
    details: string|null          # MAY

  ws_id: string|null              # MAY (WorkingSet.current_ws_id 등)
  run_id: string|null           # MAY (대표 TraceBundle)
  bucket_id: string|null         # MAY
  intent_key: string|null         # SHOULD
  state_key: string|null          # SHOULD

  produced:                       # MUST (생성/갱신된 메모리 단위 연결)
    reasoning_ids: [string]|null        # MAY (ReasoningMemoryRecord ids)
    rule_draft_ids: [string]|null       # MAY (DistillDraft.draft_id 등)
    reuse_state_ids: [string]|null      # MAY (ReuseStateRecord ids)

  action_plan_id: string|null     # MAY (MemoryActionPlan.plan_id)
  notes: string|null              # MAY
```

### MemoryActionPlan
```yaml
MemoryActionPlan:
  schema_version: "0.1.0"
  plan_id: string                 # MUST
  created_at: string              # MUST (ISO8601)

  fold_id: string|null            # MAY (FoldResult.fold_id)
  bucket_id: string|null         # MAY
  intent_key: string|null         # SHOULD
  state_key: string|null          # SHOULD

  actions:                        # MUST
    - op: "WRITE"|"PIN"|"MERGE"|"PRUNE"|"RETIRE"   # MUST
      target_store: "ReasoningBank"|"Rulebook"|"ReuseBuffer"|"TraceBundle"   # MUST
      target_ids: [string]|null   # MAY
      payload_ref: string|null    # MAY (요약/절차/프롬프트/코드 등 외부 참조)
      reason_keys: [string]|null  # MAY (집계 가능한 안정 키)
      safety:                     # MAY
        dry_run: bool|null
        ttl_days: int|null
        max_bytes: int|null

  notes: string|null              # MAY
```

### MemoryActionRecord
```yaml
MemoryActionRecord:
  schema_version: "0.1.0"
  op_id: string                   # MUST
  created_at: string              # MUST (ISO8601)

  plan_id: string|null            # MAY
  fold_id: string|null            # MAY

  op: "WRITE"|"PIN"|"MERGE"|"PRUNE"|"RETIRE"       # MUST
  status: "APPLIED"|"SKIPPED"|"FAILED"             # MUST
  target_store: string            # MUST
  target_ids: [string]|null       # MAY
  produced_ids: [string]|null     # MAY

  reason_keys: [string]|null      # MAY
  error: string|null              # MAY
```


### DistillDraft
```yaml
DistillDraft:
  schema_version: "0.1.0"
  draft_id: string              # MUST
  source_run_ids: [string]    # MUST
  proposed_rule:                # MUST (RuleRecord의 부분집합)
    type: "StrategyRule"|"GuardrailRule"
    title: string
    body: string
    applicability: object
  evidence: object              # MUST

  # v0.1.0-addendum(rev03, 이전) 강화: “설명→실패예측→반례”를 Distiller 산출물 규격으로 포함(승격 게이트에서 사용)
  failure_prediction:           # SHOULD (승격 후보라면 사실상 REQUIRED)
    mechanism: string           # SHOULD  (작동 가설: 왜 먹히는가)
    dependencies: [string]      # SHOULD  (의존성: tool/router/format/memory 등)
    predicted_failures:         # SHOULD  (최소 2개 권장)
      - id: string              # taxonomy id (예: context_dilution, instruction_conflict...)
        description: string
        triggers: [string]
        severity: "low"|"med"|"high"

  # v0.1.0-addendum(rev03, 이전) 강화: Micro-Regression 팩 선택(테스트 자동 생성용)
  micro_regression_packs: [string]  # MAY (예: ["FORMAT","TOOL","BUDGET","CONTEXT_LEARNING"])

  tests:                        # MUST
    regression_tests: [string]        # SHOULD (micro-regression 포함 권장)
    counterexample_tests: [string]    # SHOULD (>=2: cluster 1 + boundary 1 권장)
```




### PatterningPlan (optional extension) — Patterning(데이터 개입) 오프라인 산출물 계약

> 목적: “원하는 행동/일반화”를 만들기 위해 **데이터 믹싱/가중치**를 역으로 설계한다.
> 런타임 컴포넌트가 아니라, Distiller/Trainer가 로그/회귀 결과를 기반으로 만드는 **오프라인 레시피**다.

```yaml
PatterningPlan:
  schema_version: "0.1.0"
  patterning_id: string                 # MUST
  generated_at: string                  # MUST (ISO8601)
  base_dataset: string                  # MUST (예: distill_v3, regress_v2)

  # 개입 레버: 데이터 슬라이스/생성기/템플릿의 혼합 비율
  probes:                               # MUST (K개)
    - probe_id: string                  # MUST
      description: string               # SHOULD
      slice_query: string|null          # MAY  (bucket_id/reason_code/tag 등)
      max_weight: float|null            # MAY  (상한, 클립용)

  # 관측치(Observable): Rulecraft에서는 내부 구조 대신 “행동 프록시”로 둔다
  observables:                          # MUST (I개)
    - obs_id: string                    # MUST
      kind: "pass_rate"|"unknown_rate"|"reason_code_rate"|"avg_cost"|"custom"
      bucket_id: string|null           # MAY
      reason_code: string|null          # MAY (kind=reason_code_rate)
      target_value: float|null          # MAY (절대 목표)
      target_delta: float|null          # MAY (상대 목표, dμ_target)

  chi_estimation:                       # MUST
    method: "finite_diff"|"grad_proxy"  # MUST
    epsilon: float|null                 # SHOULD (finite_diff일 때)
    regularizer: float|null             # SHOULD (pinv 안정화: ridge)
    condition_number: float|null        # MAY
    notes: string|null                  # MAY

  solution:                             # MUST (dh)
    weights: [float]                    # MUST (probes와 같은 길이)
    clipped: bool                       # MUST
    renormalized: bool                  # MUST

  validation:                           # MUST
    canary_suite_id: string|null        # SHOULD
    replay_window: object|null          # MAY
    rollback_on_regress: bool           # MUST
    results: object|null                # MAY (pass/unknown/cost 변화 요약)

  applied: bool                         # MUST
  notes: string|null                    # MAY
```

#### PatterningPlan 규범
- `PatterningPlan`은 **MUST** 오프라인에서만 생성/적용한다.
- 적용은 **MUST** `replay → canary → rollback`(Playbook §15.6) 순서를 따른다.
- `weights`는 **MUST** 클립/정규화(폭주 방지) 후 기록한다.
- `reason_code_rate`를 observable로 쓸 경우, Validator는 taxonomy를 안정적으로 유지하는 것을 **SHOULD** 한다(Validator Spec §5.5).

---


### RegressionTestSpec
```yaml
RegressionTestSpec:
  schema_version: "0.1.0"
  test_id: string                 # MUST
  test_type: "regression"|"counterexample"   # MUST
  severity: "critical"|"normal"              # SHOULD

  # 입력 참조: 기존 input_ref 유지(SSOT). 필요 시 prompt를 inline으로 둘 수도 있음(옵션).
  input_ref: string                   # MUST
  prompt: string|null             # MAY (포터블/오픈소스 배포용으로 inline 제공 가능)

  # v0.1.0-addendum(rev03, 이전) 강화: Micro-Regression 자동 채점을 위한 assertion(가능한 경우)
  assert:                         # MAY
    type: "json_schema"|"regex_present"|"regex_absent"|"tool_called"|"tool_not_called"|"length_lte"|"exact_match"|"contains"
    args: object

  # v0.1.0-addendum(rev03, 이전) 강화: 반례는 최소한 cluster/boundary를 구분하면 운영이 편해짐
  kind: "cluster"|"boundary"|"transform"|null   # MAY

  tags: [string]|null            # MAY (예: ["context_dilution","format_leak"])
  expected:
    must_pass: bool               # MUST
    notes: string|null            # MAY
  linked_rule_ids: [string]       # SHOULD
```


### RolloutSummary
```yaml
RolloutSummary:
  schema_version: "0.1.0"
  summary_id: string            # MUST
  run_id: string              # MUST (요약이 생성된 실행 trace)

  answer: string                # MUST (한 줄 답 후보)
  key_reasoning:                # MUST (핵심 근거 1~3줄)
    - string
  assumptions:                  # SHOULD (가정/해석 포인트)
    - string
  checks:                       # SHOULD (반례/엣지/검증 포인트)
    - string
  confidence: float             # SHOULD (0~1)

  validator_score: float|null     # MAY (ValidationResult.score 미러)
  selection_score: float|null    # MAY (top-m 선택 점수: score+diversity-penalty)
  repr:                          # MAY (RepSpace 참조; 요약 공간 TTS용)
    encoder_id: string|null
    dim: int|null
    summary_vec_id: string|null

  validator_mirror:              # SHOULD (요약 생성 시점의 검증 요약)
    verdict: "PASS"|"FAIL"|"PARTIAL"
    outcome: "OK"|"FAIL"|"UNKNOWN"

  compaction_policy:            # SHOULD
    max_tokens: int|null        # SHOULD (요약 상한)
    forbid_cot: bool            # MUST (true 권장)
    format: string|null         # MAY (template id)
```


### SearchNodeRecord (optional extension) — EPS/GTS 노드 로그

> 목적: EPS/GTS에서 “어떤 분기(노드)가 왜 선택/가지치기 되었는지”를 RunLog보다 더 세밀하게 남기기 위한 노드 로그.
> - RunLog.context_eng.tree_search는 요약 메타만 남긴다.
> - 상세 트리는 SearchNodeRecord를 별도 스토어(파일/DB)에 저장하고 node_store_ref/search_id로 연결하는 것을 권장한다.

```yaml
SearchNodeRecord:
  schema_version: "0.1.0"
  search_id: string                # MUST (한 번의 search session)
  node_id: string                  # MUST (search 내 유일)
  parent_node_id: string|null      # MAY
  branchpoint_id: string|null      # MAY (예: "bp_context_select_v1")
  depth: int|null                  # MAY
  stage: string|null               # MAY (예: "router:context_select", "tool:call", "compose")

  run_id: string|null            # SHOULD (이 노드에서 실행된 trace(RunLog/TraceBundle) 조인 키)

  selection_score: float|null      # MAY (Validator+cost 합성 점수)
  validator:                        # MAY
    verdict: "PASS"|"FAIL"|"PARTIAL"|null
    outcome: "OK"|"FAIL"|"UNKNOWN"|null
    score: float|null
    failure_cluster_id: string|null

  cost:                            # MAY
    tokens_total: int|null
    latency_ms: int|null
    tool_calls: int|null

  status: "expanded"|"killed"|"leaf"|"best"|null  # MAY
  kill_reason: string|null         # MAY (stable key: "l1_violation"|"outcome_fail"|"budget"|"exception")
  notes: string|null               # MAY
```


### FlowMapSnapshot
```yaml
FlowMapSnapshot:
  schema_version: "0.1.0"
  generated_at: string                 # MUST
  window:
    start_at: string                   # MUST
    end_at: string                     # MUST
  bucket_id: string                   # MUST

  estimator:                           # MAY
    kind: string                        # 예: "aggregate_v1" | "nn_field_v1" | "cat_flow_map_v1"
    model_ref: string|null              # MAY (아티팩트 id/path/hash)
    feature_set: string|null            # MAY (입력 피처 세트 id)
    calibration: string|null            # MAY (보정/캘리브레이션 메모)

  risk:                                # MUST
    stage_hotspots:                    # SHOULD (상위 K개)
      - stage: string                  # 예: main→verify, compose→verify
        reason_code: string|null       # 예: format_leak, tool_misroute
        risk_rate: float               # (verdict∈{FAIL,PARTIAL} OR outcome∈{FAIL,UNKNOWN}) 비율
        support_n: int                 # 표본 수

  opportunity:                         # MUST
    interventions:                     # SHOULD
      - intervention: string           # 예: SelfReview-1pass, K_probe, K_full+compose
        gain_pass: float               # 개입 전후 PASS 회복(또는 품질 상승) 추정
        delta_cost: float              # 추가 비용(토큰/지연/툴콜 등) 추정
        efficiency: float              # gain_pass / max(delta_cost, ε)
        support_n: int

  notes: string|null                   # MAY
```

### ContextBlock (optional extension) — selective injection unit (Selective Context Injection)

> 목적: 룰/정책/메모리 힌트/PRAXIS 전술을 “질의별로 필요한 조각만” 주입할 수 있게 **원자 단위**로 정규화한다.

```yaml
ContextBlock:
  schema_version: "0.1.0"
  context_id: string                     # MUST (안정적 ID)
  text: string                      # MUST (원문, 원자 규칙/정의/지침 1개)
  tags: [string]|null               # MAY  (도메인/툴/스테이지 태그)
  priority: int|null                # MAY  (충돌 시 우선순위)
  conflicts_with: [string]|null     # MAY  (상충 ContextBlock id 목록)
  source_ref: string|null           # MAY  (예: SSOT/Policy/Rulebook/Memory 등 출처)
  applicability_hints: object|null  # MAY  (키워드/슬롯/정규식 등 cheap filter 힌트)
```

### SieveExample (optional extension) — (q, applicable CUs) 학습/회귀 데이터 단위

> 목적: SieveGenPlan이 생산하는 최소 데이터 단위. Distiller/RegressionPack이 소비한다.

```yaml
SieveExample:
  schema_version: "0.1.0"
  example_id: string                # MUST
  generated_at: string              # MUST (ISO8601)
  query: string                     # MUST (q 또는 q')
  applicable_context_ids: [string]       # MUST
  rejected_context_ids: [string]|null    # MAY
  unknown_context_ids: [string]|null     # MAY
  seed_refs: [string]|null          # MAY (seed query/cluster/plan ref)
  notes: string|null                # MAY (필요하면 intent/provenance 요약을 짧게; 상세는 해당 생성 런의 RunLog/ValidationResult에 남기고 seed_refs로 연결)
```

### SieveGenPlan (optional extension) — ContextBlock 기반 합성 쿼리 생성 레시피

> 목적: seed few-shot + ContextBlock 조합으로 합성 질의를 만들고, 적용성 검증을 거쳐 `SieveExample`을 생산하는 오프라인 레시피다.

```yaml
SieveGenPlan:
  schema_version: "0.1.0"
  sieve_plan_id: string                   # MUST
  generated_at: string                    # MUST (ISO8601)

  # seed
  seed_queries: [string]                  # MUST (대표 질의 K개; 실패/애매 케이스 포함 권장)
  seed_failure_cluster_ids: [string]|null # MAY

  # ContextBlock sampling
  context_source: string|null                  # MAY (예: rulebook_v?, memory_bank_v?)
  context_sampling:
    k_min: int|null                       # SHOULD (예: 3)
    k_max: int|null                       # SHOULD (예: 5)
    tag_mix: object|null                  # MAY  (예: {tool:web:0.3, tool:fs:0.2, ...})
    avoid_conflicts: bool                 # MUST

  # generation/verification
  generator_model_ref: string|null        # MAY
  validator_model_ref: string|null         # MAY (L2-Applicability)
  l0_filter_enabled: bool                 # MUST
  l2_applicability_enabled: bool          # MUST
  budgets:
    target_distinct_queries: int|null     # SHOULD
    max_examples: int|null                # SHOULD

  # outputs
  output_dataset_id: string|null          # SHOULD (예: sieve_examples_v1)
  validation:
    replay_suite_id: string|null          # MAY
    canary_suite_id: string|null          # MAY
    rollback_on_regress: bool             # MUST
```

### InfoMechanicsLedger (optional extension)

> Infomechanics(2601.15028) 개념을 Rulecraft 운영 로그로 옮긴 “프록시 ledger”다.
> 완전한 Bayesian posterior를 요구하지 않는다. **일관된 추정/비교 가능성**이 목적이다.

```yaml
InfoMechanicsLedger:
  schema_version: "0.1.0"
  enabled: bool|null                 # MAY

  # PASS belief (추정)
  p_pass_prior: float|null           # MAY
  p_pass_post: float|null            # MAY

  # surprisal / information gain (bits)
  surprisal_bits_prior: float|null   # MAY  # -log2(p_pass_prior)
  surprisal_bits_post: float|null    # MAY  # -log2(p_pass_post)
  info_gain_bits: float|null         # MAY  # prior - post

  # 비용 대비 정보이득(정책/스케일링)
  delta_cost: float|null             # MAY  # tokens 또는 latency 등 공통 cost 단위
  ig_per_cost: float|null            # MAY  # info_gain_bits / max(delta_cost, ε)

  # “정보 지형” 프록시: 다중 모드/울퉁불퉁함
  phi_proxy: float|null              # MAY
  mode_count_eff: float|null         # MAY

  notes: string|null                 # MAY
```



### ReuseStateRecord
```yaml
ReuseStateRecord:
  schema_version: "0.1.0"
  state_id: string                       # MUST (예: "rs_01H...")
  created_at: string                     # MUST (ISO8601)
  bucket_id: string|null                # MAY
  seed_summary: string                   # MUST (짧은 상태 요약. 비밀/민감정보 금지)
  seed_prompt: string|null               # MAY (프롬프트 prefix로 직접 쓰고 싶다면)
  source_run_ids: [string]|null        # MAY (어떤 로그에서 유래했는지)
  rule_set_hash: string|null             # MAY (주입된 룰 집합의 해시/버전)

  validator:                              # MAY
    verdict: "PASS"|"PARTIAL"|"FAIL"|null
    outcome: "OK"|"UNKNOWN"|"FAIL"|null
    score: float|null
    score_method: string|null

  reward:                                # MAY (Execution-grounded loop과 정렬)
    total: float|null
    pass: float|null
    cost: float|null
    diversity: float|null
    consistency: float|null

  exec_ok: bool|null                     # MAY
  exec_failure_class: string|null        # MAY

  lineage:                               # MAY
    parent_state_id: string|null
    parent_ids: [string]|null
    mutation_ops: [string]|null

  counters:                              # MAY (PUCT용)
    N: int|null                          # 선택 횟수(노드 방문)
    last_used_at: string|null

  ttl: string|null                       # MAY (예: "days:7")
  tags: [string]|null                    # MAY
```


### ConditionalTacticRecord (Phase 3)
```yaml
ConditionalTacticRecord:
  schema_version: "0.1.0"
  tactic_id: string                    # MUST
  created_at: string                   # MUST (ISO8601)
  bucket_id: string|null              # MAY
  intent_key: string|null              # MAY
  state_key: string|null               # MAY

  status: "active"|"pinned"|"retired"  # MUST
  ttl: string|null                     # MAY (예: "days:14")
  last_used_at: string|null            # MAY

  summary: string                      # MUST (짧은 전술 요약)
  injection:                           # MUST (주입 단위)
    mode: "prepend"|"inline"|null      # MAY
    content: string                    # MUST (짧은 절차/체크리스트/힌트)

  predicates: [string]|null            # MAY (간단 조건식/태그)
  evidence:                            # MAY
    run_ids: [string]|null
    validator_ids: [string]|null

  metrics:                             # MAY
    pass_p_hat: float|null
    efficiency_est: float|null         # (gain/cost) 추정
    avg_cost: float|null
    use_n: int|null
    fail_n: int|null

  embedding_ref: string|null           # MAY
  payload_ref: string|null             # MAY
```

### ReuseBuffer
```yaml
ReuseBuffer:
  schema_version: "0.1.0"
  buffer_id: string                      # MUST
  policy_id: string                      # MUST
  max_size: int                          # MUST
  eviction: "lru"|"score_decay"|"hybrid"|null     # MAY

  # Phase 2까지: 탐색/롤아웃 재시드용 seed/prior
  seed_entries: [ReuseStateRecord]       # MUST

  # Phase 3(PRAXIS): 조건부 전술(힌트/절차) 저장소
  tactic_entries: [ConditionalTacticRecord]   # MUST

  stats:                                 # MAY
    seed_size: int|null
    tactic_size: int|null
    last_compact_at: string|null
```


### ReuseSelectMeta
```yaml
ReuseSelectMeta:
  schema_version: "0.1.0"
  enabled: bool
  policy: string
  selected_state_id: string|null
  selected_score: float|null
  puct:
    c: float|null
    Q_method: "max_reward"|"mean_reward"|null
    P_method: "rank_prior"|"uniform"|null
    Q: float|null
    P: float|null
    T_total: int|null
    N: int|null
```



### WorkingSetRecord / WorkingSet
```yaml
WorkingSetRecord:
  schema_version: "0.1.0"
  ws_id: string                    # MUST
  run_id: string|null            # MAY (현재 런과 연결)
  bucket_id: string|null          # SHOULD
  intent_key: string|null          # MAY
  state_key: string|null           # MAY

  status: "active"|"retired"       # MUST
  ttl: string|null                 # MAY (예: "session", "hours:6")
  updated_at: string|null          # MAY

  # 현재 fold의 핵심 중간상태(작게 유지)
  facts: [string]|null             # MAY (확정 사실)
  assumptions: [string]|null       # MAY (가정)
  constraints: [string]|null       # MAY (제약)
  decisions: [string]|null         # MAY (분기/선택)
  open_questions: [string]|null    # MAY (미해결)

WorkingSet:
  schema_version: "0.1.0"
  current_ws_id: string|null       # MAY
  stack: [string]|null             # MAY (ws_id 스택)
```

### ReasoningMemoryRecord / ReasoningBank
```yaml
ReasoningMemoryRecord:
  schema_version: "0.1.0"
  memory_id: string                # MUST
  kind: "episode"|"tactic"         # MUST
  created_at: string               # MUST
  updated_at: string|null          # MAY

  bucket_id: string|null          # SHOULD
  intent_key: string|null          # SHOULD
  state_key: string|null           # MAY

  status: "active"|"pinned"|"retired"|"temporary"  # MUST
  ttl: string|null                 # MAY

  summary: string                  # MUST (짧은 재사용 단위)
  tags: [string]|null              # MAY (domain/tool/output/constraint 등)
  run_ids: [string]|null         # MAY (근거 TraceBundle/RunLog 연결)

  # 품질/가성비 통계(옵션)
  pass_p_hat: float|null           # MAY (0~1, 경험적 성공률)
  avg_cost: float|null             # MAY (상대값/정규화 가능)
  last_used_at: string|null        # MAY

  embedding_ref: string|null       # MAY (벡터 저장 참조)
  payload_ref: string|null         # MAY (상세 절차/코드/프롬프트 등 외부 참조)

ReasoningBank:
  schema_version: "0.1.0"
  bank_id: string                  # MUST
  policy: string|null              # MAY (예: "episodic+tactic_v1")
  max_items: int|null              # MAY
  items: [ReasoningMemoryRecord]   # MUST
```

### MemoryRecallRequest/Response (RECALL 계약)
```yaml
MemoryRecallRequest:
  schema_version: "0.1.0"
  request_id: string               # MUST
  run_id: string|null            # MAY
  query: string                    # MUST (리콜 질의/요구)
  bucket_id: string|null          # SHOULD
  intent_key: string|null          # MAY
  state_key: string|null           # MAY
  sources: [string]|null           # MAY (기본: ReasoningBank/Rulebook/ReuseBuffer)
  top_k: int|null                  # MAY
  filters: object|null             # MAY (status/ttl/tool/output 등)

MemoryHint:
  memory_id: string                # MUST
  source: string                   # MUST ("ReasoningBank"|"Rulebook"|"ReuseBuffer"|"TraceBundle")
  score: float|null                # MAY
  reason: string|null              # MAY (왜 올라왔는지)
  summary: string|null             # MAY (주입 가능한 짧은 요약)
  run_ids: [string]|null         # MAY

MemoryRecallResponse:
  schema_version: "0.1.0"
  request_id: string               # MUST
  items: [MemoryHint]              # MUST
  method: string|null              # MAY
  fallback_used: bool|null         # MAY
```

### SandboxPolicy
```yaml
SandboxPolicy:
  schema_version: "0.1.0"
  enabled: bool                # SHOULD
  image_id: string|null        # SHOULD (docker image digest/tag)
  network: "off"|"allowlist"|"on"  # SHOULD
  allowlist: [string]|null     # MAY
  caps:                        # SHOULD
    max_turns: int|null
    wall_ms: int|null
    cpu_ms: int|null
    mem_mb: int|null
    disk_mb: int|null
  toolset: ["execute_bash","str_replace_editor","submit"]  # SHOULD (논문 기본)
  workdir: string|null         # MAY (예: /testbed)
```


### SandboxActionTrace
```yaml
SandboxActionTrace:
  schema_version: "0.1.0"
  run_id: string             # MUST (RunLog.run_id와 연결)
  action_id: string            # MUST
  turn: int                    # MUST
  tool: "execute_bash"|"str_replace_editor"|"submit"   # MUST
  args: object                 # SHOULD (민감정보는 redaction)
  obs:
    ok: bool                   # MUST
    exit_code: int|null        # MAY
    stdout_digest: string|null # SHOULD (해시/요약)
    stderr_digest: string|null # SHOULD
    error_class: string|null   # MAY
  io:
    files_read: [string]|null      # MAY
    files_written: [string]|null   # MAY
    bytes_read: int|null           # MAY
    bytes_written: int|null        # MAY
  net:
    used: bool|null                # MAY
    fetch_n: int|null              # MAY
    domains: [string]|null         # MAY
```

### 5.6 운영 정합성 최소 계약(불변식) — base(hotfix14p8)

> 이 절은 “튜닝”이 아니라 **운영 의미가 흔들리면 전체 지표/회귀/승격이 무의미해지는 것**만 고정한다.

#### 5.6.1 L2/L2.5 신호의 사용 범위(판결 vs 라우팅)
- IntentSatisfaction(L2a) / 의미 grader(L2) / ProvenanceProbe(L2.5)는 **판결이 아니라 라우팅 신호**다.
- L2/L2.5가 할 수 있는 일:
  - `violated_constraints`에 안정 키 추가
  - `score_evidence`에 근거/탐침 결과 기록
  - `should_escalate`/`clarify` 분기 입력 제공
- L2/L2.5는 `outcome`을 `OK/FAIL`로 확정할 수 없다. 확정은 L3 실행 검증만 한다.

#### 5.6.2 Intent-first 정책(기본)
- `INTENT:NOT_SATISFIED` 또는 `INTENT:PARTIAL`이 발생하면,
  - 기본 정책은 K 확장보다 **명확화/분해/산출물 슬롯 보강**이다.
  - (권장) Orchestrator는 `control_signals.exit_reason="clarify"`(또는 동급 토큰)으로 기록한다.

#### 5.6.3 Provenance 오염 방지 게이트(기본)
- `PROVENANCE:LIKELY_KNOWN`이 발생하면,
  - 기본 정책은 Patterning/Distiller 입력 및 Rulebook 승격으로의 **편입 금지**
  - HumanGate 또는 추가 근거가 생길 때까지 보류한다.
- `PROVENANCE:NOT_CHECKED`는 hot-path에서 정상일 수 있다(리소스 정책). 필요 시 probe/full에서만 수행한다.

#### 5.6.4 로그 불변식(집계/회귀/FlowMap을 위한 최소 기록)
BudgetController/early-exit/should_escalate이 개입한 런은 아래를 `RunLog.control_signals`에 기록하는 것을 권장한다.

- `budget_tier` (hot/probe/full)
- `budget_caps` (적용된 상한)
- `early_exit`, `exit_stage`, `exit_reason`

> 임계값(EWMA/윈도우/컷) 자체는 SSOT에 고정하지 않는다(프로파일/실측로 관리).
