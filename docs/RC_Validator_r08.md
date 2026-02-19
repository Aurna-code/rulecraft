# Rulecraft Validator 제작 사양 — r08

- 버전: r08
- 작성일: 2026-01-26 (Asia/Seoul)
- 수정일: 2026-02-18 (Asia/Seoul)
- 패치:
  - TongGeometry(GTS) — LLM 가이드 트리 서치(형식-검증 도메인) 이식
  - NN-FT(2601.14453) — FlowMap 신호를 ‘추정기’로 확장하는 근거(옵션)
  - Categorical Flow Maps(2602.12233) — 범주형 정책/개입 분포를 few-step 추정기로 증류 + test-time guidance(옵션)
  - CL-bench(2602.03587) — ContextLearningProbe(루브릭 기반) + CONTEXT_LEARNING violated_constraints + CLPack v1 RegressionTestSpec 템플릿(결정적 우선) 추가
  - Phase 2 — Folding + Memory Actions 신호/정합성 규율 추가
  - Phase 3 — PRAXIS(조건부 전술) 신호 규율 추가
  - hotfix09(원천) — InFi-Check FGFC(근거/오류타입/교정) 확장(`ValidationResult.fgfc`) 규격 추가
  - hotfix12 — Patterning(데이터 개입) 입력 신호로서 reason_codes 안정성 규범 추가
  - hotfix12p1 — Validator/Router 무(無)모델 기본값 + 에스컬레이션 지표/트리거(관측 가능성) 추가
  - hotfix14 — Selective Context Injection: ContextBlock 적용성(L2-Applicability) + 합성 데이터 레일(SieveGenPlan) 연결
  - hotfix14p4 — Selective Context Injection 운영 최소 계약(context_select.version + 불변식 위반 처리) 정리
  - hotfix14p5 — Offline NavigatorGraph(오프라인) + HotPathBudget 상한 + early-exit(초기 디폴트)
  - Infomechanics(2601.15028) — evidence→p_pass 업데이트 + IG/Cost ledger hook(옵션)
  - hotfix14p7(2601.22401) — IntentSatisfaction(meaningful correctness) + ProvenanceProbe(prior-art/출처) 신호 추가
  - hotfix14p8(base) — 운영 정합성 최소 계약(신호 범위/Intent-first/오염 방지/집계 키 드리프트 방지) 명문화
  - hotfix14p9 — Verification gap(UNKNOWN) 명문화 + Canary/rollback 프로토콜 구체화 + ContextBlock conflict 결정적 처리 규율
  - ENCOMPASS(2512.03571) — EPS record_score 매핑(ValidationResult.score) + group-eval(pairwise_rank) 활용 지침 추가
  - Reasoning Failures Survey(2602.06176) — RobustnessProbe(transform) + ROBUSTNESS 키/로깅 규범(옵션)
  - TKDE DataPrep Survey(2601.17058) — DataPrepHarness(L3) + DATA_PREP violated_constraints taxonomy(옵션) 추가
  - SMEL(2602.05182) — collab_distill/teacher 출력 데이터셋 생성 시 PASS/OK 중심 필터링 규율(옵션)

> 목적: Rulecraft의 `ValidatorAdapter`를 “추정”이 아니라 **프로그래밍적 실체**로 만들기 위한 구현 스펙을 고정한다.
> 반환 계약(SSOT): `RC_Contracts_SSOT_ssot10.md` 의 `ValidationResult`

---

## 0) TL;DR

- Validator는 단일 모델 프롬프트가 아니라 **3층 합성(Compose)** 이 기본이다.
  - **L1 정적(필수)**: 스키마/형식/제약/툴콜 규칙 검증 (결정적)
  - **L2 의미(선택)**: 저비용 grader로 타당성/정합성 스코어링 (확률적)
  - **L3 실행(옵션, 강추)**: Sandbox/하네스로 실행·채점해서 outcome을 확정 (결정적)
- 약한 모델일수록 L2를 “믿음”으로 쓰지 말고, **L1+L3로 정답을 환경에서 뽑게** 만드는 편이 가성비가 좋다.

---

## 0.1) 모델 없는 기본값(권장) — “가벼운 미들웨어” 운영 규율

Rulecraft의 기본 목표는 **Validator/Router를 별도 AI 모델 없이** 굴리는 것이다.
즉, “판단”을 모델에게 떠넘기기보다 **결정적 신호(L1/L3) + 관측 가능 로그**로 운영을 안정화한다.

### 기본 프로파일(권장)
- **ValidatorProfile: `v_l1_only`** (기본)
  - L1 정적 검증만 수행(스키마/제약/툴콜/금지 패턴)
  - `outcome=UNKNOWN`은 정상(=검증 불가)이며, PASS 정의(SSOT §5.1)로 운영한다
- **ValidatorProfile: `v_l1+l3_exec`** (가능한 도메인)
  - L1 + L3 실행 검증(테스트/프로버/샌드박스)로 `outcome ∈ {OK, FAIL}`을 가능한 한 확정
- **L2 의미 검증은 기본 OFF**
  - 붙이더라도 “최종 판결”이 아니라 **선별/스케일링 트리거(should_escalate)** 신호로만 쓴다
  - 초경량 1순위는 `score_method="rule_check"`(정규식/간단 함수/키 검사)이다

### Router/Policy도 “무(無)모델” 우선
### early-exit / 예산 상한(HotPathBudget)과 Validator의 경계
- early-exit/예산 상한은 Validator의 판정이 아니라 **Orchestrator/BudgetController의 제어 정책**이다.
- 단, 어떤 경우에도 **L1 정적 검증은 MUST 수행**하고, 종료 사유/적용 티어는 `RunLog.control_signals`에 기록한다(SSOT hotfix14p5).

- Router/BudgetController/should_escalate은 기본적으로 **규칙 기반(결정적)** 으로 만든다.
- 입력 신호는 `RunLog + ValidationResult(reason_codes/violated_constraints/outcome) + cost`로 충분하다.

### “불가피해지면 가볍게 다는” 기준(에스컬레이션 지표)
아래 지표가 일정 기간(윈도우)에서 반복될 때만 L2(또는 더 강한 검증)를 고려한다.

- **UNKNOWN 과다**: `unknown_rate`가 높고, 그 원인이 `exec_unavailable_rate`/`sandbox_denied`가 아니라 “의미 검증 부재”로 보일 때
- **반복 FAIL 클러스터**: 동일 `failure_cluster_id`가 높은 빈도로 재발(=룰/포맷/툴 정책 개선이 더 급함)
- **근거 빈약 반복**: `insufficient_evidence_rate`가 높고, “L3로 확정할 수 없는 텍스트 태스크”가 병목일 때
- **컨텍스트 오염**: `memory_overinject` / `praxis_tactic_overinject` 같은 신호가 반복(=Router/주입 정책이 문제)
- **도메인 특화 판정 필요**: 예컨대 자연어 요약 품질 같은 “실행으로 확정 어려운” 영역에서만 제한적으로 L2를 붙인다

> 핵심: L2를 붙이기 전에, 먼저 L1(계약/형식/툴)과 L3(하네스/테스트)로 “확정 가능한 것”부터 확정한다.

## 0.2) 운영 정합성 최소 계약(불변식) — base(hotfix14p8)

> 이 절은 “튜닝”이 아니라 **구현체/운영체가 서로 다르게 해석하면 시스템이 깨지는 부분**만 고정한다.
> 임계값/가중치/윈도우는 프로파일(config)로 분리하고, 여기서는 **의미/순서/기록 규율**만 확정한다.

### MUST: L1은 항상 수행한다
- 어떤 티어(hot/probe/full)에서도 **L1 정적 검증은 MUST** 수행한다.
- early-exit가 걸려도 L1을 생략하면 안 된다(=형식/툴 규약 위반이 런타임으로 새어나감).

### MUST: L2/L2.5는 “판결”이 아니라 “라우팅 신호”다
- **L2 의미 검증 / L2a IntentSatisfaction / L2.5 ProvenanceProbe는 verdict/outcome의 최종 진실이 아니다.**
- L2/L2.5가 낼 수 있는 건:
  - `violated_constraints`(안정 키) 추가
  - `score_evidence` 채움(설명/근거/탐침 결과)
  - `should_escalate` 입력 신호 제공
- L2/L2.5는 `outcome`을 `OK/FAIL`로 **확정할 수 없다**(확정은 L3 실행 검증만).

### MUST: Intent는 “K를 늘려서” 해결하지 않는다(기본 정책)
- `INTENT:NOT_SATISFIED` 또는 `INTENT:PARTIAL`이 떴다면,
  - 기본 정책은 **명확화/분해/산출물 슬롯 보강**이며,
  - K-drafts/probe/full 승격은 “의도 명확화가 끝난 뒤”에만 한다.
- 이 경우 Orchestrator는 `RunLog.control_signals.exit_reason="clarify"`(또는 동급 토큰)을 기록하는 것을 권장한다(SSOT §RunLog).

### MUST: Provenance는 “오염 방지 게이트”다
- `PROVENANCE:LIKELY_KNOWN`이 떴다면, 기본 정책은:
  - Patterning/Distiller 입력(회귀/증류 데이터)으로 **편입 금지**
  - Rulebook 승격/메모리 저장은 **HumanGate 또는 추가 근거**가 생길 때까지 보류
- `PROVENANCE:NOT_CHECKED`는 핫패스에서 정상이다(=리소스 정책). 다만 novelty/주장 강도가 높으면 probe 티어로 승격할 수 있다(Playbook §6.1).

### MUST: 집계 키는 안정적이어야 한다
- `violated_constraints`는 자유 서술이 아니라 **taxonomy 키**로 남긴다(SSOT §5.2).
- 새 키를 추가할 땐:
  - (a) ValidatorSpec taxonomy에 등록
  - (b) FlowMap/회귀 집계 코드 갱신
  - (c) 문서 패치 노트에 기록
  을 함께 수행한다(“키만 늘리고 집계를 안 고치는” 드리프트 금지).

### SHOULD: UNKNOWN은 “타입(원인)”이 있어야 한다 (운영 안정성)

- `outcome == "UNKNOWN"`인 경우, reason_codes 또는 violated_constraints 중 최소 1개로 “왜 UNKNOWN인지”를 남기는 것을 SHOULD 한다.
  - 예: `sandbox_timeout | sandbox_denied | exec_unavailable | insufficient_evidence | env_nondeterminism | search_budget_exhausted | prover_incomplete`
- 원인 없는 UNKNOWN(= untyped UNKNOWN)은 클러스터링/회귀/FlowMap에서 해석 불능으로 남아,
  결국 “모델을 더 붙일지/하네스를 더 붙일지/명확화를 할지” 결정을 망친다.


## 1) 범위와 비범위

### 1.1 범위
- Orchestrator가 호출 가능한 `ValidatorAdapter.verify(...)`의 인터페이스/합성 규칙 정의
- L1/L2/L3의 역할 분해, verdict/outcome/score 산출 규칙 정의
- reason_codes/violated_constraints 최소 taxonomy 정의
- Sandbox(LLM-in-Sandbox) 연동 시 Validator가 무엇을 확정해야 하는지 정의

### 1.2 비범위
- 특정 모델(예: GPT-계열/Claude/로컬)의 “최적 프롬프트”는 SSOT에 포함하지 않는다(프로파일 파일로 분리 권장).
- 도메인별 전문 평가(human eval)는 Rulecraft의 기본 Validator 범위를 벗어난다(추가 Validator로 붙일 수는 있음).

---

## 2) ValidatorAdapter 인터페이스 (권장)

### 2.1 입력(권장 시그니처)
```python
class ValidatorAdapter:
    def verify(
        self,
        *,
        run_id: str,
        input_ref: str,
        candidate: object,              # y0 / compose 결과(텍스트 또는 tool-call 결과)
        context: dict,                  # impact_level/domain_tag/user_clarity 등
        constraints: dict | None = None,# 길이/포맷/툴 정책/금지사항 등
        artifacts: dict | None = None,  # sandbox 결과 파일/테스트 로그/요약 등
        meta: dict | None = None,       # model/meta/cost/draft_select 등
    ) -> dict:  # ValidationResult
        ...
```

### 2.2 출력(반드시 지켜야 할 것)
- 반환은 **반드시** `RC_Contracts_SSOT_ssot10.md` 의 `ValidationResult` 형태여야 한다.
- 특히 아래 필드는 **MUST**:
  - `validator_id`
  - `verdict ∈ {PASS, FAIL, PARTIAL}`
  - `outcome ∈ {OK, FAIL, UNKNOWN}`
- (옵션) 도큐먼트 기반/팩트 기반 검증에서는 `ValidationResult.fgfc`(SSOT의 FGFCReport)를 채워 **근거+오류타입+교정안**을 구조화해 남길 수 있다.

---

## 3) 1/2/3층 상세

## 3.1 L1: 정적 검증 (필수)

### 3.1.1 역할
- “모델이 아무리 말을 잘해도” 어길 수 있는 것들을 **결정적으로** 잡는다.
- 대표:
  - 구조화 출력 스키마 검증(JSON/YAML)
  - 길이/필드 누락/필수 키 누락
  - 금지 패턴(키/비밀/로그 유출, 룰 우회 지시, tool 권한 상승 등)
  - 툴콜 args 스키마(필수 인자 누락/타입 불일치)
  - 명시 제약(예: “숫자 근거 3개”, “출력은 표 금지”, “파일명 규칙”, “no web”) 위반

### 3.1.2 산출
- 위반이 있으면:
  - `violated_constraints`에 제약 id/태그를 넣는다.
  - `reason_codes`에 `format_leak`, `tool_misroute`, `constraint_violation` 같은 원인을 넣는다.
  - verdict는 원칙적으로 `FAIL` 또는 `PARTIAL` (운영 정책에 따라 다름)

### 3.1.3 (옵션) RunLog.context_eng 정적 검증

`context_eng`는 “정답”이 아니라 **운영 관측 신호**다. 그래도 최소한의 스키마/열거값 검증은 L1에서 잡아두는 게 좋다.

- `context_eng.access_mode ∈ {"file_native","prompt_embed","hybrid"}`
- `context_eng.format ∈ {"yaml","md","json","toon","custom"}`
- `context_eng.enabled`가 true면 `context_eng.version`은 SHOULD(운영상 사실상 MUST)
- `domain_partition.enabled`가 true면 `domain` 또는 `shard` 중 하나는 SHOULD 존재
- `grep_tax.attempts/failed/retrieval_tokens/overhead_tokens_est`는 음수 금지

- **미래 확장 허용**: `context_eng`의 스키마 밖(알려지지 않은) 하위 키가 있어도 `context_eng_invalid`로 처리하지 않는다.
  - 구현은 MAY로 `context_eng.unknown_fields = [string]`에 “알려지지 않은 키 이름” 목록을 기록해 관측할 수 있다.
  - `unknown_fields`가 존재한다면: 배열/각 원소 string만 허용(그 외 타입이면 `context_eng_invalid`).

위반 시 처리(권장):
- `violated_constraints += ["context_eng_invalid"]`
- `reason_codes += ["constraint_violation"]`  (taxonomy 추가는 하지 말고 기존을 재사용)



---

## 3.2 L2: 의미 검증 (선택)

### 3.2.1 역할
- 텍스트 결과의 “타당성/정합성/근거 빈약/자기모순”을 확률적으로 잡는다.
- 약한 모델 환경에서는 L2를 “최종 판결”로 쓰지 말고, **승격 트리거**(should_escalate)로 쓰는 게 안전하다.

### 3.2.2 구현 옵션(가벼운 순)
- **rule_check**: 규칙 기반(키워드/정규식/간단 함수)으로 신호만 만들기
- **yes_logit**: (가능하면) 짧은 질문에 대한 yes/no 확률을 score로 사용
- **pairwise_rank**: 여러 후보(rollouts/top-m)를 비교해 순위/선호도 산출
- **hybrid**: 위 신호들을 결합해서 score(0~1)로 맵핑

### 3.2.2a (ENCOMPASS/EPS) record_score(선별 점수) 권장 매핑

EPS/GTS에서 search backend가 “무슨 후보를 확장/선택할지” 결정할 때,
`ValidationResult.score(0~1)`를 기본 record_score로 사용한다.

- MUST: score를 쓰는 경우, 동일 버킷/동일 프로파일에서 **비교 가능한 의미**(0~1)를 유지해야 한다.
- SHOULD: score가 null인 경우를 대비해, verdict/outcome 기반 fallback을 프로파일에 고정한다(문서에 임계값을 박지 말고 config로).
  - 예시(정보용):
    - PASS+OK → 1.0
    - PASS+UNKNOWN → 0.6
    - PARTIAL → 0.3
    - FAIL 또는 outcome=FAIL → 0.0

Group evaluator(ENCOMPASS) 매핑:
- `score_method="pairwise_rank"`는 top-m/beam 후보를 비교해 고르는 “집단 평가”로 사용할 수 있다.
- 단, L2는 판결이 아니다. 최종 확정은 L1/L3로 하고, L2는 선별/승격 신호로만 쓴다(§0.2 원칙 유지).


### 3.2.3 L2-Applicability: ContextBlock 적용성 판정(Selective Context Injection, 선택)

목표는 “정답/오답 판결”이 아니라, **현재 질의 q에 대해 어떤 컨텍스트 블록이 적용되는지**를 가늠해서
주입(overinject)과 상충(conflict)을 줄이는 것이다.

권장 출력(SSOT 변경 없이, `score_evidence`/`notes`에 기록):
- `score_evidence.applicability`:
  - `applicable_context_ids`: [string]
  - `rejected_context_ids`: [string]
  - `unknown_context_ids`: [string]  (애매하면 UNKNOWN으로 남긴다)
- `reason_codes`(옵션):
  - `context_overinject`: 후보가 너무 많아 컨텍스트 오염/길이 압박을 유발
  - `context_conflict`: ContextBlock 간 상충이 감지됨
  - `applicability_unknown`: 적용성이 애매해 승격 필요(should_escalate)


추가(옵션): `cat_flow_map_v1` 기반 L2-Applicability (Categorical Flow Maps, 2602.12233)
- ContextBlock 적용성을 (YES/NO/UNKNOWN 또는 p_applicable) **분포**로 예측하는 “policy hint” 구현체로 사용할 수 있다.
- 출력은 반드시 위 계약대로 `score_evidence.applicability`에 남기고, 애매하면 `unknown_context_ids`로 남긴 뒤 should_escalate 트리거로만 사용한다(판결 금지).

운영 규율:
- 약한 모델 환경에서는 L2를 “최종 판결”로 쓰지 말고 **승격 트리거**로만 사용한다(§3.2.1 원칙 준수).
- L0(cheap) 필터를 먼저 적용해 후보 CU를 top-N으로 줄인 뒤, L2는 “애매한 경계”만 다루게 한다.
- CU가 메모리/PRAXIS 전술 성격이면 기존 `memory_overinject/memory_conflict`를 우선 사용해도 된다(집계 축을 늘리지 않기 위해).

관측/로그 규약(권장, 운영 정합성):
- L2-Applicability를 실행했으면, `ValidationResult.score_evidence.applicability`에 남기는 것과 별개로 **RunLog에 미러링**한다(SSOT §RunLog의 `context_select`).
  - 최소: `candidate_context_ids / applicable_context_ids / rejected_context_ids / unknown_context_ids / injected_context_ids`
  - `context_select.version`: "context_select_v1"  (계측 계약 버전; 회귀 비교를 위해 고정)
  - 가능: `token_est.saved`(대략치)까지 남겨 “토큰 절감 vs 품질” 회귀를 가능하게 한다.
- RunLog에는 **ID만** 남긴다(ContextBlock 원문 텍스트는 TraceBundle에서만, 디버그 시에만).
- 불변식(버그 탐지): `injected_context_ids ⊆ candidate_context_ids` 이어야 하고, 가능하면 `injected_context_ids ⊆ applicable_context_ids ∪ unknown_context_ids` 를 만족해야 한다.
- 불변식이 깨지면(예: injected ⊄ candidate), **모델 문제가 아니라 Orchestrator/Logger 버그**로 간주한다.
  - `violated_constraints += ["context_select_invariant"]`
  - `reason_codes += ["constraint_violation"]`  (taxonomy 확장 없이 재사용)



### 3.2.4 L2-IntentSatisfaction: 의도(meaningful correctness) 충족 판정(선택)

L2-IntentSatisfaction은 “사실/정답”을 판정하는 게 아니라, **요청한 산출물/형식/범위가 실제로 충족됐는지**를 잡는 얇은 그레이더다.
대부분의 실무 실패는 “틀렸다”보다 “요청과 다르다”가 먼저 터진다.

권장 출력(SSOT 변경 없이, `violated_constraints` + `score_evidence`로):
- `violated_constraints`:
  - `INTENT:NOT_SATISFIED`  (요청된 산출물/형식/범위를 충족하지 못함)
  - `INTENT:PARTIAL`        (일부만 충족; 누락 슬롯/단계 존재)
- `score_evidence.intent`(권장):
  - `satisfied`: `"YES"|"PARTIAL"|"NO"|"UNCLEAR"`
  - `missing`: [string]          # 누락된 산출물 슬롯(예: `"diff_patch"`, `"citations"`)
  - `notes`: string|null

의도 슬롯의 출처(권장, 가벼운 순):
- (1) Orchestrator의 TaskSpec/IOContract (있으면 최우선)
- (2) ContextBlock의 `NavigatorUnit.entries[*].must_have`
- (3) 질의에서 슬롯을 추출하는 cheap rule(키워드/정규식) + (필요 시) 짧은 yes_logit

운영 규율(중요):
- `INTENT:NOT_SATISFIED`는 K 증설로 해결되는 경우가 드물다.
  - 기본 정책은 **K 확장 금지 + 명확화/분해(Planner)로 되돌리기**(Playbook §6.1).
- high impact에서는 `INTENT:PARTIAL`도 승격 트리거로 취급한다(대외 발송/되돌리기 어려운 작업 등).

### 3.2.5 L2.5-ProvenanceProbe: 선행/출처 탐침(prior-art/citation) (선택)

ProvenanceProbe는 “정답 여부”가 아니라 **novelty(새 주장) 리스크**와 **인용/출처 누락**을 잡는다.
메모리/증류/회귀 데이터 레일이 있는 시스템에서는, 이 신호가 없으면 *자기오염*이 쌓인다.

권장 출력(SSOT 변경 없이, `violated_constraints` + `score_evidence`로):
- `violated_constraints`:
  - `PROVENANCE:NOT_CHECKED`        # 체크를 수행하지 못함(핫패스 기본)
  - `PROVENANCE:CITATION_MISSING`   # 인용 요구가 있는데 누락
  - `PROVENANCE:LIKELY_KNOWN`       # 유사 선행이 강하게 감지됨(오염 방지 게이트)
  - `PROVENANCE:NEEDS_HUMAN_REVIEW` # 자동 판정 불가
- `score_evidence.provenance`(권장):
  - `mode`: `"none"|"local_index"|"web"|"hybrid"`
  - `queries`: [string]|null
  - `top_hits`: [object]|null        # 제목/출처/요약/유사도 등(원문 과다 인용 금지)
  - `novelty`: `"NOVEL"|"LIKELY_KNOWN"|"UNCLEAR"`
  - `notes`: string|null

실행 티어(권장):
- **hot tier**: 기본 OFF → `PROVENANCE:NOT_CHECKED`만 남겨도 된다.
- **probe/full tier**: 1~2 query + top hit 요약 수준의 얕은 탐침만(비용 캡).
- **high impact / 대외발송 / novelty 주장**: 필요 시 `PROVENANCE:NEEDS_HUMAN_REVIEW`로 HumanGate 승격.

운영 규율(오염 방지):
- `PROVENANCE:LIKELY_KNOWN`은 “틀렸다”가 아니다. **‘새롭다’ 주장에 대한 리스크 표기**다.
- 이 키가 찍힌 산출물은 기본 정책으로:
  - 메모리 저장/Patterning/회귀팩 편입에서 제외(또는 별도 격리 레일로만 저장)
  - 필요하면 “출처/선행을 붙여 재서술”로 전환한다.


---

### 3.2.6 L2-ContextLearningProbe: 컨텍스트 학습/루브릭 기반 평가 (CL-bench, 2602.03587) (선택)

CL-bench(2602.03587)가 강조하는 실패는 “긴 컨텍스트를 **찾았는가**(retrieval)”가 아니라,
컨텍스트에 있는 새 지식/규칙/절차를 **학습해서 적용했는가**(context learning)다.

Rulecraft에서는 이걸 “최종 판결”로 쓰지 않고, 아래처럼 **표준 키 + 루브릭 통계**로만 남겨서
FlowMap/회귀팩/Router 개선에 연결하는 것을 권장한다.

#### 입력(권장)
- `artifacts.rubrics[]` 또는 `task_spec.rubrics[]`: 요건/체크리스트(verification rubrics)
- (가능하면) `meta.context_learning`: `category/subcategory`, `prior_conflict_expected`, `turn_idx` 등

#### 출력(SSOT 변경 없이)
- `violated_constraints`(권장 키; SSOT §5.2.4 참고)
  - `CONTEXT_LEARNING:NOT_LEARNED`
  - `CONTEXT_LEARNING:PRIOR_KNOWLEDGE_OVERRIDE`
  - `CONTEXT_LEARNING:INCOMPLETE`
  - `CONTEXT_LEARNING:TURN_DEPENDENCY_BROKEN`

- `score_evidence.context_learning`(권장)
  - `category/subcategory`
  - `rubrics_total/passed/failed`
  - `prior_override: bool`
  - `notes: string|null`

- (권장) 루브릭을 **FGFC로 인코딩**할 수 있다:
  - `ValidationResult.fgfc`에 `FGFCReport.unitization="rubric"`
  - 각 루브릭 항목을 unit으로 두고, `SUPPORTED/REFUTED/NOT_ENOUGH_INFO`를 각각 `충족/위반/불명`으로 해석한다.

#### CLPack v1 연동(offline regression): rubrics → assert 우선

Rulecraft의 목표는 “루브릭을 잘 채점하는 모델”이 아니라, **운영 가능한 회귀팩**이다.
따라서 CL-bench식 루브릭이 들어오면 우선순위는:
1) `RegressionTestSpec.assert`로 내릴 수 있는 항목은 **결정적으로 채점**(regex/json_schema/tool 정책)
2) 정말 남는 서술형 항목만 L2(ContextLearningProbe)의 얇은 판정으로 보조

권장 루브릭 타입(= assert 템플릿):
- required_token → `regex_present`
- forbidden_token → `regex_absent`
- required_params → `json_schema`
- tool_required / tool_forbidden → `tool_called` / `tool_not_called`
- multiturn(이전 결과 재사용) → `contains` / `exact_match`

권장 로깅(SSOT §5.2.4):
- critical required_token/required_params 실패 → `CONTEXT_LEARNING:NOT_LEARNED`
- 비치명 누락(절차/예외/설명) → `CONTEXT_LEARNING:INCOMPLETE`
- prior_conflict 컨텍스트에서 forbidden_token 등장 → `CONTEXT_LEARNING:PRIOR_KNOWLEDGE_OVERRIDE`
- 멀티턴 의존 검사 실패 → `CONTEXT_LEARNING:TURN_DEPENDENCY_BROKEN`

`score_evidence.context_learning`에 아래를 남기면 회귀/클러스터가 쉬워진다(권장):
- `rubrics_total/passed/failed`
- `failed_ids: [string]` (rubric_id 또는 test_id)
- `fail_types: [string]` (예: required_token/required_params/tool_policy)
- `prior_override: bool`

(참조) CLPack 템플릿은 Playbook §15.5.1, Addendum §3.8.2.3에 예시로 제공한다.


#### 구현 옵션(가벼운 순)
- `score_method="rule_check"`: 정규식/키/숫자/포맷 검증으로 **결정적** 체크(가능하면 최우선)
- `yes_logit` 또는 초경량 grader: rule_check로 못 잡는 “서술적 루브릭”만 얇게 판정
- `hybrid`: 루브릭을 (deterministic 가능한 것 / 의미 판정 필요한 것)으로 분해해 혼합

#### 운영 규율(중요)
- hot-path 기본 OFF(회귀/카나리/should_escalate tier에서만 사용 권장).
- `CONTEXT_LEARNING:PRIOR_KNOWLEDGE_OVERRIDE`가 뜬 산출물은 기본 정책으로:
  - Memory write / Rulebook 승격 / Patterning 입력에 **편입 금지**(오염 방지)
- 멀티턴 의존성 실패(`TURN_DEPENDENCY_BROKEN`)는 모델 문제가 아니라 Orchestrator/WorkingSet/RECALL 버그일 수 있다.
  - 따라서 이 키를 찍을 때는 `TraceBundle.refs`에 “이전 turn 산출물 ref”를 함께 남기는 것을 권장한다(디버깅/회귀 가능성).


## 3.3 L3: 실행 검증 (옵션, 강력 추천)

### 3.3.1 역할
- “말로 검증이 안 되는 것”을 **실행/채점**으로 확정한다.
- 대표:
  - (형식-검증 가능한 도메인) **심볼릭 프로버/정리증명기 연동**: 증명 가능/불가능/미결을 outcome(OK/FAIL/UNKNOWN)으로 매핑
  - 코드/수식/데이터 처리: 테스트 하네스 실행, 정답 파일 생성/비교
  - 툴체인 작업: 파일 생성 여부, 명령 성공 여부, 메트릭 계산
  - 장문 컨텍스트 처리: sandbox에서 파일로 분리/요약/검증 후 결과만 반영

### 3.3.2 산출 규칙(중요)
- 실행 하네스가 PASS/FAIL을 명확히 주면:
  - `outcome`은 **OK/FAIL로 확정**한다(UNKNOWN 금지).
  - verdict는 보통 outcome을 따른다(단, L1에서 치명 위반이면 FAIL 유지).
- 실행이 불가능(타임아웃/권한/환경 미지원)이면:
  - `outcome=UNKNOWN` + `reason_codes`에 `sandbox_timeout|sandbox_denied|exec_unavailable` 중 하나를 남긴다.

### 3.3.3 (권장) DataPrepHarness — “로컬 문맥 + 전역 제약”을 붙이는 실행형 검증

데이터 준비(Data Preparation: cleaning/integration/enrichment)는 **텍스트 판정(L2)만으로는** 안정적으로 확정하기 어렵다.
가장 흔한 실패는:
- 로우/셀만 보고 고치다가 **전역 제약(유니크/분포/참조무결성)** 을 깨뜨림
- 결측값/설명/프로파일을 “그럴듯하게” 생성하지만 **근거가 없음**(hallucinated cleaning/enrichment)
- 매칭에서 **대칭성/추이성** 같은 전역 불변식이 깨짐

따라서 data_prep 도메인은 L3 하네스가 “옵션”이 아니라 **가성비 좋은 기본 보험**이 된다.

#### (A) 입력/출력 형태(권장)
- 입력:
  - `input_ref`: 원본 데이터(파일/테이블/샘플) 참조
  - 후보 산출물: (1) 변환 코드(pandas/sql), (2) 규칙/제약(정규식/FD/타입), (3) 매칭 결과(mapping/pairs), (4) 프로파일/설명(+근거)
- 출력:
  - `outcome`: OK/FAIL/UNKNOWN (가능하면 OK/FAIL로 확정)
  - `violated_constraints`: 아래 (C) 키를 안정적으로 기록
  - `score_evidence.data_prep`: task/granularity/metrics/evidence(SSOT §ValidationResult.score_evidence)

#### (B) 실행형 체크(권장 최소)
- **전역 통계/제약 계산**(샘플/전체 가능): null rate, unique rate, 빈도 상위값, 분포, 타입 추정, 간단한 의존성 힌트
- **변환 적용 후 diff/제약 검증**:
  - 스키마(컬럼/타입) 불변/허용 변경인지
  - row count 변화(허용인지)
  - UNIQUE/NOT NULL/REGEX/DOMAIN(허용 값) 같은 제약 위반
- **통합(integration) 불변식 체크**:
  - symmetry: match(A,B) == match(B,A)
  - transitivity: A~B, B~C 이면 A~C (클러스터 기반일 때)
- **보강(enrichment) 근거 체크**:
  - 생성된 주장/요약이 (a) 샘플 row, (b) 쿼리 결과, (c) 외부 출처 중 최소 1개에 링크되는지

> 구현 팁: “LLM이 직접 표를 다 읽는 것” 대신, 하네스가 전역 신호를 계산해 LLM에게 주는 쪽이 싸고 튼튼하다.

#### (C) 표준 violated_constraints 키(SSOT §5.2.3 권장)
- `DATA_PREP:SCOPE:GLOBAL_VIEW_REQUIRED`
- `DATA_PREP:CONSTRAINT:VIOLATION[:<type>:<field>]`
- `DATA_PREP:INTEGRATION:SYMMETRY_BROKEN`
- `DATA_PREP:INTEGRATION:TRANSITIVITY_BROKEN`
- `DATA_PREP:ENRICHMENT:UNSUPPORTED_CLAIM`

#### (D) UNKNOWN을 줄이는 운영 규율(권장)
- 하네스가 “환경 미지원”이라면 UNKNOWN은 정상이다. 다만 **원인 타입은 MUST**:
  - `reason_codes += sandbox_timeout|sandbox_denied|exec_unavailable`
- 하네스가 있음에도 UNKNOWN이 잦다면, 대개 “입력/산출물 포맷”이 애매하다.
  - 출력 계약을 좁힌다: *변환 코드 + 적용 범위 + before/after 샘플 + rollback 가능성*.

---

## 4) 합성 규칙 (L1/L2/L3 → ValidationResult)

### 4.1 우선순위(권장)
1) **L1 치명 위반**(보안/권한/포맷 필수) → verdict=FAIL (outcome은 L3가 확정했더라도 FAIL 유지 가능)
2) L3 실행 결과가 있으면 → outcome 확정(OK/FAIL)
3) L2는 (a) score 산출, (b) PARTIAL/UNKNOWN 트리거, (c) 후보 선별(top-m) 신호로 사용

### 4.2 verdict/outcome 기본 매핑(권장)
- **PASS**: (L1 pass) AND (L3 없거나 OK) AND (L2가 큰 경고를 내지 않음)
- **FAIL**: (L1 치명 위반) OR (L3 outcome=FAIL) OR (L2가 강한 FAIL 신호)
- **PARTIAL**: L1은 통과했지만, L2/L3가 애매하거나 일부 제약만 위반한 경우

- **outcome=OK**: 실행/근거가 충분해 “맞음”을 확인했거나, 검증이 명확한 경우
- **outcome=FAIL**: 실행/근거로 “틀림”이 확인된 경우
- **outcome=UNKNOWN**: 검증 불가(정보 부족/실행 불가/근거 빈약) 상태

> 주의: `outcome=UNKNOWN`은 “틀림”이 아니라 “확정 불가”다. L1이 통과했고 치명 경고가 없으면, **`verdict=PASS + outcome=UNKNOWN`을 허용**해서 Orchestrator가 결과 출력을 막지 않게 한다.
> FAIL은 (a) L1 치명 위반, (b) L3로 오답 확정(outcome=FAIL), (c) L2가 강한 FAIL 신호를 낸 경우로 좁게 유지하는 게 운영 안정성이 좋다.

> 시스템 PASS 정의는 `PASS iff (verdict==PASS) AND (outcome!=FAIL)` 를 사용한다(Playbook/Addendum의 정의 유지).

### 4.3 score(0~1) 권장 규칙
- score는 “최종 신뢰도”가 아니라 **선별/스케일링/정책 입력**이다.
- 권장:
  - L3가 명확 PASS면 score=1에 가깝게 캡(예: 0.95~1.0)
  - L3 FAIL이면 score=0에 가깝게 캡
  - L3 없으면 L2 score를 사용하되, L1 경미 위반이 있으면 penalty 적용




### 4.4 (옵션) Infomechanics hook — evidence → p_pass 업데이트 + IG/Cost 기록

> Validator는 “최종 판사”가 아니라, Orchestrator/Router가 의사결정할 수 있게 **증거를 계량화**하는 센서다.
> Infomechanics(2601.15028)의 핵심을 Rulecraft식으로 번역하면: “증거가 들어오면 surprisal이 줄고, 줄어든 만큼을 정보이득으로 기록할 수 있다.”

권장: Validator는 아래를 **추정치로만** 계산해서 RunLog에 남긴다(SSOT `InfoMechanicsLedger`).

- `p_pass_prior` → `p_pass_post` (PASS 확률 추정)
- `info_gain_bits := -log2(p_prior) - (-log2(p_post))`
- `ig_per_cost := info_gain_bits / max(delta_cost, ε)`

#### 4.4.1 구현 프록시(권장, 모델 없는 버전)

`log_odds = log(p/(1-p))` 를 내부 상태로 들고, 증거마다 가산한다.

- L1 치명 위반(보안/권한/스키마 필수) → `log_odds += -6` (거의 FAIL)
- L3 테스트/하네스 PASS → `log_odds += +6` / FAIL → `log_odds += -6`
- L2 score(0..1, 선택) → `log_odds += α*(score - 0.5)` (α는 작게: 1~2)

그리고 `p = sigmoid(log_odds)` 로 `p_pass_post`를 얻는다.

#### 4.4.2 왜 이게 쓸모 있나
- Router가 “스케일링을 더 했는데 정보가 안 늘었다”를 로그로 확인할 수 있다.
- `mode_count_eff`(rollout 다양도)와 같이 보면, **‘다중 모드라서 탐색 확장’** 과 **‘정보가 안 늘어서 중단’** 을 분리할 수 있다.

주의:
- 이건 수학적으로 ‘정답’인 posterior가 아니다. **일관된 정책 신호**가 목표다.
- high impact에선 L2를 믿지 말고 L3(실행/테스트) 비중을 키우는 편이 낫다.

### 4.5 노이즈/비결정성 처리 규율(권장)

LongCat-Flash-Thinking-2601의 “노이즈 분해” 관점(환경/툴이 완전하지 않다는 전제)을 Rulecraft에 가져오면, Validator는 아래를 **일관되게** 처리해야 한다.

- **툴 실패/부분 성공**
  - 툴 실행 실패/타임아웃이면: `reason_codes += tool_failure|tool_timeout`, 필요 시 `violated_constraints += TOOL:EXEC_FAILED|TOOL:EXEC_TIMEOUT`
  - 부분 성공이면: `reason_codes += partial_success`, 결과는 “가능한 범위”로만 반영(과신 금지)
- **툴 출력 불량**
  - 출력 스키마 위반이면: `reason_codes += tool_output_invalid`, `violated_constraints += TOOL:OUTPUT_INVALID`
  - 동일 조건 재실행 상충이면: `reason_codes += tool_output_inconsistent`
- **환경(샌드박스/테스트) 플래키**
  - 동일 입력/시드에서 결과가 흔들리면: `reason_codes += env_nondeterminism`, `outcome=UNKNOWN`을 기본으로 두고
    Orchestrator에 “재현성 확보(시드 고정/반복 실행/환경 핀)” 또는 “상위 검증 경로”로 승격 신호를 준다.
- **재시도 복구**
  - 1회 재시도로 정상화되면: `reason_codes += retry_recovered`
  - 단, high impact에서는 `PASS/OK`로 끝내지 말고(정책에 따라) 추가 검증/재현성 체크를 권장한다.

> 원칙: “노이즈를 숨기지 않는다.”
> Validator는 불확실을 `UNKNOWN`으로 남기고, Orchestrator가 `should_escalate/EnvSuite/회귀`로 해결하게 만드는 쪽이 운영 안정성이 높다.


---



### 4.6 (2602.06176) RobustnessProbe — 변형(transform) 스윕으로 “숨은 취약성”을 노출(옵션)

*Large Language Model Reasoning Failures* (TMLR 01/2026; arXiv:2602.06176)는
“겉보기로는 그럴듯하지만, **사소한 변형에 의해 결과가 뒤집히는 실패**”를 **robustness issue**로 분리해 다룬다.

Rulecraft 관점에서 이건 좋은 소식이다. “정답을 잘 맞추는가”보다 운영에 중요한 건,
**같은 의미를 다른 방식으로 말해도(또는 약간만 교란해도) 시스템이 흔들리지 않는가**이기 때문이다.

#### 4.6.1 핵심 아이디어(운영형)
- 원본 질의 q에 대한 답 y 하나만 채점하면, hidden vuln을 놓친다.
- 그래서 q를 **의미 보존 변형(transform)** 몇 개로 바꾼 q'들을 만들고,
  산출물의 **불변식(invariant)** 을 검사한다.

#### 4.6.2 권장 절차(핫패스에 무리 없는 “얇은” 버전)
1) baseline 실행: q → y0
2) transform 생성: q → {q1,q2,q3}  (2~4개 권장, 비용 상한)
3) 재실행: qi → yi
4) 불변식 검사(가능한 한 결정적으로):
   - **형식 불변식**: JSON/YAML 스키마, must-have 슬롯, 금지 토큰 등(L1로 대부분 처리)
   - **툴 불변식**: tool policy(호출 필수/금지/순서/args) 위반 여부
   - **핵심 결론 불변식**: 최종 숫자/선택지/코드 실행 결과 등(가능하면 L3/하네스로 확정)
5) 불일치면(권장 기본값):
   - `reason_codes += self_inconsistency`
   - `violated_constraints += ROBUSTNESS:VARIATION_SENSITIVE`
   - `outcome=UNKNOWN`을 기본으로 두고 `should_escalate` 승격
     (High impact면 L3/EnvSuite로 확정하는 쪽을 권장)

#### 4.6.3 TransformSuite(권장 최소)
아래 변형들은 논문에서 자주 언급되는 “작은 변화인데도 성능이 흔들리는 요인”을 운영형으로 옮긴 것이다.

- `transform:reword` : 질문을 약간만 바꿔 말하기(동의어/어순/표현)
- `transform:perspective` : 1인칭↔3인칭, 서술 관점 전환
- `transform:verbosity` : 같은 요구를 더 짧게/더 길게(길이·상세도)
- `transform:distractor` : 무관 정보 1~2문장 삽입(교란 내성)
- `transform:reverse_relation` : 관계를 뒤집은 질문(“A is B” ↔ “B is A”)
  - 이 변형에서 깨지면 `violated_constraints += ROBUSTNESS:REVERSAL_CURSE`도 함께 기록을 권장한다.
- `transform:order_shuffle` : 전제/조건 목록의 순서만 바꾸기(순서 편향 탐침)

- (data_prep 옵션) `transform:swap_pair` : (A,B) 입력 쌍의 순서만 바꾸기(매칭 대칭성 탐침)
- (data_prep 옵션) `transform:schema_permute` : 스키마/컬럼 목록 순서를 섞기(순서 민감도 탐침)

#### 4.6.4 로깅 규율(SSOT 호환)
- `score_evidence.robustness`에 probe_used/invariants/mismatch/mismatch_on을 기록한다(SSOT는 object payload 허용).
- “분류”는 판결이 아니라 힌트다. 필요하면 `score_evidence.failure_taxonomy`에 아래를 기록한다.
  - `reasoning_type`: informal|formal|embodied
  - `failure_type`: fundamental|limitation|robustness
  - `category`: 예) cognitive_bias / reversal_curse / compositional_reasoning …

## 5) reason_codes & violated_constraints (최소 taxonomy)

### 5.1 reason_codes(권장 최소)
- `format_leak` (포맷 밖 텍스트/구조 누수)
- `constraint_violation` (명시 제약 위반)
- `insufficient_evidence` (근거 부족)
- `instruction_conflict` (지시 상충)
- `tool_misroute` (툴 종류/시점/순서/args 오류)
- `tool_failure` (툴 실행 실패: 권한/리밋/서버 오류 등)
- `tool_timeout` (툴 타임아웃/장시간 지연)
- `tool_output_invalid` (툴 출력이 스키마/형식 위반)
- `tool_output_inconsistent` (동일 조건 재실행 시 출력 상충)
- `partial_success` (일부 단계 성공, 일부 실패)
- `truncation_or_cutoff` (출력 잘림/중단 의심)
- `numeric_error` (계산/수치 오류 의심)
- `self_inconsistency` (자기모순/상충 진술)

- (옵션, FGFC) `fact_predicate_mismatch` / `fact_entity_mismatch` / `fact_circumstance_mismatch`
- (옵션, FGFC) `fact_coreference_mismatch` / `fact_discourse_link_mismatch` / `fact_extrinsic_claim`
- (옵션, FGFC) `fact_refuted` / `fact_supported` / `fact_not_enough_info`  (unit 단위 verdict 집계용)

- `env_nondeterminism` (실행/채점이 비결정적·플래키)
- `search_budget_exhausted` (트리/탐색 예산 소진으로 결론 미확정)
- `prover_incomplete` (프로버/하네스가 불완전: UNKNOWN 유지)
- `proof_not_found` (증명/해결 실패: outcome=FAIL로 확정한 경우)
- `retry_recovered` (재시도로 복구 성공: 신뢰도 penalty 신호)
- `sandbox_timeout` / `sandbox_denied` / `exec_unavailable` (실행 검증 실패 원인)
- `test_fail` (하네스/테스트 실패로 명확한 오답)
- (옵션, Phase 2/3) `memory_recall_miss` / `memory_overinject` / `memory_conflict` / `memory_stale` / `memory_poison_risk` (메모리 주입/리콜/PRAXIS 조건부 전술 관련 신호)
- (옵션, hotfix14) `context_overinject` / `context_conflict` / `applicability_unknown` (ContextBlock 적용성/주입 신호; 필요 시 memory_*로 대체 가능)
- (옵션, Phase 3) `praxis_tactic_mismatch` / `praxis_tactic_overinject` / `praxis_tactic_conflict` (조건부 전술 특화 신호; 위 memory_*로도 충분하면 생략 가능)

### 5.2 violated_constraints(권장 형태)
- 문자열 id로 기록(예: `SCHEMA:ValidationResult`, `POLICY:NO_NETWORK`, `FORMAT:JSON_ONLY`, `TOOL:CALL_REQUIRED:web.search_query`)
- 운영에서 중요한 건 “사유의 텍스트”보다 **집계 가능한 키**다(FlowMap/Regression에 사용).

#### 5.2.1 안정성 규율(권장)
- `violated_constraints`에 들어가는 키는 **taxonomy.py에 등록된 집합**(또는 동일한 하드코딩 목록)에서만 선택한다.
- 자유 서술 텍스트를 넣지 않는다(집계 불가 + 회귀 불가).
- 키 체계 변경이 필요하면: (1) taxonomy 버전 업, (2) 집계/회귀 코드 동시 업데이트, (3) `failure_cluster_id` 리매핑을 같이 수행한다.
- `failure_cluster_id`는 아래 규칙으로 **결정적으로(deterministic)** 생성하는 것을 권장한다.
  - 입력: `sorted(reason_codes)`, `sorted(violated_constraints)`, `stage_tag`(예: `main|verify`, `compose|verify`, `tree|verify`)
  - 생성: `sha1("rc=" + ",".join(rc) + "|vc=" + ",".join(vc) + "|st=" + stage_tag)`의 hex digest
  - 목적: 로그 집계/회귀팩/우선순위 자동화를 위해 “같은 실패는 같은 키”로 묶는다.


#### 5.2.1.1 (hotfix14p7) Intent/Provenance 키(권장 추가)

- **INTENT**
  - `INTENT:NOT_SATISFIED`
  - `INTENT:PARTIAL`
- **PROVENANCE**
  - `PROVENANCE:NOT_CHECKED`
  - `PROVENANCE:CITATION_MISSING`
  - `PROVENANCE:LIKELY_KNOWN`
  - `PROVENANCE:NEEDS_HUMAN_REVIEW`

주의:
- 위 키들은 reason_codes 확장을 피하기 위해 `violated_constraints`로만 표준화한다.
- 세부 근거/상위 유사 문헌 목록은 `score_evidence.provenance` 또는 `notes`로 남긴다(집계 키는 작게).

#### 5.2.1.2 (2602.06176) ROBUSTNESS 키(권장 추가, 옵션)

Robustness probe(§4.6)에서 “의미 보존 변형”에 의해 결과가 흔들리는 것이 확인되면,
아래 키를 `violated_constraints`에 남겨 **클러스터링/회귀팩/패턴링** 입력으로 쓴다.

- `ROBUSTNESS:VARIATION_SENSITIVE`
- `ROBUSTNESS:REVERSAL_CURSE`  (reverse_relation 변형에서 깨진 경우에만 추가 권장)


#### 5.2.1.3 (TKDE 2025; 2601.17058) DATA_PREP 키(권장 추가, 옵션)

데이터 준비는 “의미가 그럴듯함”보다 **제약/근거/전역 일관성**이 중요하다.
따라서 아래 키들을 `violated_constraints`로 표준화해두면, FlowMap/회귀팩/패턴링에서 원인 분해가 빨라진다.

- `DATA_PREP:SCOPE:GLOBAL_VIEW_REQUIRED`
  - row/cell 로컬 컨텍스트로만 해결하려다, 유니크/분포/집계 상관/참조무결성 같은 전역 신호가 필요한 상태
- `DATA_PREP:CONSTRAINT:VIOLATION[:<type>:<field>]`
  - 예: `...:UNIQUE:email`, `...:NOT_NULL:order_id`, `...:REGEX:date_yyyy_mm_dd`, `...:DOMAIN:country_code`
- `DATA_PREP:INTEGRATION:SYMMETRY_BROKEN`
- `DATA_PREP:INTEGRATION:TRANSITIVITY_BROKEN`
- `DATA_PREP:ENRICHMENT:UNSUPPORTED_CLAIM`

권장 증거 기록(SSOT 변경 없이 `score_evidence`로):
- `score_evidence.data_prep`: {task/subtask/granularity/metrics/evidence}


---



### 5.2.2 FGFC error_type taxonomy (InFi-Check 호환, 권장)

FGFC 모드에서는 `fgfc.units[*].error_type`을 아래 값 중 하나로 기록한다.

- `PredE`: predicate/관계 오류
- `EntE`: entity 오류
- `CircE`: 시간/장소/수치 등 circumstance 오류
- `CorefE`: 지시/대명사 등 co-reference 오류
- `LinkE`: 인과/시간/담화(disourse) 링크 오류
- `OutE`: 문서 밖(extrinsic) 정보 주입

권장 매핑(집계/루프용):
- PredE → `fact_predicate_mismatch`
- EntE  → `fact_entity_mismatch`
- CircE → `fact_circumstance_mismatch`
- CorefE→ `fact_coreference_mismatch`
- LinkE → `fact_discourse_link_mismatch`
- OutE  → `fact_extrinsic_claim`

주의:
- `violated_constraints`는 “정적 규칙 위반”이고, FGFC는 “의미/사실 오류”에 가깝다. 섞지 말고 각각의 채널로 남겨라.


## 5.3 Memory RECALL(Phase 1)용 상태 신호 규율

Rulecraft Phase 1에서는 RECALL의 `state_key`/호환성 판단에 Validator 신호를 쓴다(SSOT §4.3~§4.4).
그래서 Validator는 “그때그때 기분”으로 reason_codes를 바꾸면 안 된다.

권장 규칙:

- **reason_codes는 “작고 안정적인 카테고리”로 유지**(세부는 notes로)
- 최소한 아래 축은 지속적으로 분리되게 유지:
  - `format/*` (스키마/형식/출력 요구 위반)
  - `constraint/*` (명시 제약 위반)
  - `tool/*` (툴 사용 규칙/순서/권한 위반)
  - `evidence/*` (근거/인용/출처 부족)
  - `logic/*` (모순/연역 오류/수학 오류 등)
  - `execution/*` (샌드박스/하네스 실행 실패/불일치)
  - `uncertainty/*` (검증불가/불충분)

RECALL 쪽에서의 사용 예:
- 최근 런이 `tool/*`로 자주 실패하면 “tool-heavy 전술”을 우선 리콜하거나, 반대로 같은 전술


## 5.4 Folding + Memory Actions(Phase 2)용 신호 규율 (권장)

Phase 2는 Validator를 “채점기”로만 쓰지 않고, **메모리 운영 자동화의 센서**로도 사용한다.
따라서 아래 신호는 가능한 한 **작고 안정적인 키**로 reason_codes/violated_constraints에 남긴다.

권장 reason_codes(옵션):
- `memory_recall_miss`: RECALL로 가져온 힌트/전술이 실제로 도움이 안 됨(또는 부적합)
- `memory_overinject`: 힌트 과다로 컨텍스트 오염/길이 압박/혼란 유발
- `memory_conflict`: 복수 힌트/전술이 상충
- `memory_stale`: 오래된 전술/룰이 현재 state_key와 부적합
- `memory_poison_risk`: 반복 실패/위반을 유발하는 후보(RETIRE/PRUNE 후보)

권장 violated_constraints 키(예시):
- `MEMORY:RECALL_MISS`
- `MEMORY:OVERINJECT`
- `MEMORY:CONFLICT`
- `MEMORY:STALE`
- `MEMORY:POISON_RISK`

사용 방식(권장):
- Folding 트리거 중 `fail_cluster`는 위 키들의 반복을 집계해 발동할 수 있다.
- MemoryActionPlanner는 위 신호를 이용해 `RETIRE`/`PIN`/`MERGE`/`PRUNE`의 우선순위를 조정한다.
- 키는 §5.2.1 안정성 규율을 따른다(새 키 추가는 “천천히”, 기존 키 의미 변경 금지).

을 페널티 처리
- `format/*`이 반복되면 출력 스키마 관련 룰/에피소드(템플릿)를 우선 리콜

즉, Validator taxonomy는 이제 **관측 가능성 + 메모리 라우팅 신호**다. 잘 정의해두면 시스템이 알아서 개선 루프를 돈다.



## 5.5 Patterning(데이터 개입) 지원 규범(옵션)

Patterning(arXiv:2601.13548)은 “원하는 행동/일반화”를 만들기 위해 **어떤 데이터 슬라이스를 얼마나 섞을지**를 역으로 푸는 접근이다.
Rulecraft에선 이를 **Distiller/CounterexampleGenerator의 데이터 믹싱**에 적용할 수 있고, 이때 `reason_codes`는 관측치(Observable)의 핵심 입력이 된다.

따라서 Validator는 아래 규범을 **SHOULD** 지킨다.

- `reason_codes` taxonomy는 **자주 바꾸지 않는다.** (시간축 비교가 깨지면 χ 추정이 무의미해진다.)
- `reason_codes`는 “현상”이 아니라 **원인/개입 레버** 중심으로 정의한다.
  예: `format_leak`, `tool_misroute`, `missing_constraint`, `hallucinated_fact` 처럼 *데이터/룰/라우팅으로 고칠 수 있는 단위*.
- Validator는 reason_code를 과잉 생성하지 말고 **지배적인 1~3개**만 반환한다.
- 새로운 code를 추가할 때는 기존 code와 **상호배타성/우선순위**를 명시한다(다중 라벨이면 최소한 순서를 고정).
- `violated_constraints`는 “어떤 계약이 깨졌는지”를 가리키는 **결정적 키**로 유지한다(자동 회귀/게이트 입력).

### 5.5.1 (2602.05182) SMEL/collab_distill 데이터셋 게이트(옵션)

모델 협업 시스템(teacher) 출력으로 단일 모델(student)을 증류(SFT/LoRA)할 때,
ValidationResult는 “평가”가 아니라 **라벨/데이터 필터**로도 쓰인다.

권장 규율:
- **MUST** `distill_dataset`에 들어가는 teacher 샘플은 기본적으로 `PASS && outcome=="OK"` 이어야 한다.
  - 이유: UNKNOWN/환각을 섞으면 student가 “그럴듯한 오답”을 빠르게 학습한다.
- **SHOULD** `PASS && outcome=="UNKNOWN"`을 포함시키려면, UNKNOWN 원인이 “정보 부족/검증 불가”로 명확하고 오염 위험이 낮은 경우만 제한적으로 허용한다.
- **MUST** format/tool-policy 위반 샘플은 teacher라도 기본 학습셋에 섞지 않는다.
  - 필요하면 별도 슬라이스로 격리해서 “하지 말아야 할 것(negative)”로만 쓴다.
- **SHOULD** multi-student KD(teacher : best_student : self 혼합)를 쓸 때,
  - `best_student` 선정은 ValidationResult.score/PassRate(버킷별) 기반으로 고정(임의 선택 금지)
  - 혼합 비율(α:β:γ) 변화는 PatterningPlan으로 기록하고 canary로만 반영한다.

---


---


## 6) 제작 사양(코드 구조 권장)

### 6.1 모듈 구조(권장)
```
src/rulecraft/validator/
  base.py              # ValidatorAdapter 인터페이스
  l1_static.py         # schema/constraints/tool-policy validators
  l2_grader.py         # LLM grader / hybrid scoring
  l3_exec.py           # sandbox harness integration
  compose.py           # 합성(aggregation) 로직
  taxonomy.py          # reason_codes / constraint ids
```

### 6.2 최소 의존성(예시)
- L1: `jsonschema`, `pydantic`(또는 자체 validator), `re`
- L3: sandbox runner(Docker/프로세스), timeout/cgroup(가능하면), 파일 경로 정책

### 6.3 캐시/재현성(권장)
- 같은 입력(input_ref) + 같은 후보(output_ref/hash)에 대해 validator 결과를 캐시할 수 있다(비용 절감).
- 캐시 키에는 `validator_id`와 `schema_version`을 포함해야 한다(SSOT 변경 시 무효화).

---

## 7) MVP 제작 체크리스트(현실 버전)

- [ ] L1: 출력 포맷(JSON/YAML) + 필수 키 + 금지 패턴 + 길이 제한 검증
- [ ] L1: `violated_constraints`/`reason_codes`를 키 기반으로 남김
- [ ] L2: (선택) cheap grader 1개(로컬 or API 보험)만 붙여 score 산출
- [ ] L3: (선택) 최소 하네스 1개(예: 파이썬 테스트 실행)로 outcome 확정
- [ ] 합성: L1/L2/L3 우선순위 규칙을 compose.py에 고정
- [ ] 로그: RunLog에 validator verdict/outcome/score를 미러링(FlowMap용)
