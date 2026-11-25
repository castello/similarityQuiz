# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트

한글 단어 유사도 퀴즈(꼬맨틀 방식). 숨은 2글자 명사를 맞히는 정적 웹 게임이다. 힌트 5개(유사어 4 + 반의어 1)가 틀릴 때마다 하나씩 공개되고, 제출한 단어마다 정답과의 유사도(%)를 보여준다. 빌드 시스템, 테스트, 린터는 없다.

## 명령어

```sh
# 게임 실행 (file:// 로 열면 fetch가 막혀 데이터를 못 읽는다)
cd web && python3 -m http.server 8000     # http://localhost:8000

# 데이터 재생성 (web/data/vocab.json, vectors.bin 덮어씀; 네트워크 필요, 약 1분)
.venv/bin/python scripts/build_data.py
```

`.venv`에는 `numpy`, `kiwipiepy`가 있다(Python 3.14). 새로 만들 때는 `python3 -m venv .venv && .venv/bin/pip install numpy kiwipiepy`.

## 아키텍처

두 단계로 나뉜다: **오프라인 전처리(Python) → 정적 페이지(브라우저)**. 서버 로직은 없고, 유사도 계산은 전부 브라우저에서 한다.

**`scripts/build_data.py`** — fastText `cc.ko.300.vec.gz`를 스트리밍으로 읽는다(1.2GB 전체를 받지 않고 `SCAN_LINES`줄에서 멈춤). 빈도순 파일이라 줄 번호가 곧 빈도 순위이고, 이 순서가 `words` 인덱스가 된다.
- 어휘 필터: 한글 2~6자 + Kiwi 분석 결과가 단일 `NNG`이면서 `not oov`인 단어만. `oov`가 사전에 없는 이름·음차를 걸러내는 핵심 장치다(고유명사 `NNP`도 제외).
- 정답: `scripts/antonyms.txt`의 반의어 쌍에서 어휘에 둘 다 있고 2글자인 단어. (`ANSWER_POOL` 상수는 현재 쓰이지 않는다.)
- 정답별로 유사어 상위 5개를 미리 뽑는다(정답 글자를 포함하거나 정답에 포함되는 단어는 제외). 반의어는 후보 중 코사인이 가장 높은 것 하나.

**산출물 `web/data/`** (생성물이므로 직접 편집하지 않는다)
- `vectors.bin`: 단어별 L2 정규화 벡터를 int8로 양자화(`×127`), 행 우선, 300차원.
- `vocab.json`: `words`(빈도순), `answers`(words 인덱스), `hints[정답] = [[인덱스, 코사인]×5]`, `ants[정답] = [인덱스, 코사인]`.

**`web/index.html`** — 단일 파일(HTML+CSS+JS). 추측 단어의 코사인은 `vectors.bin`으로 브라우저에서 직접 계산한다.
- **점수 환산** (`score()`): 정답이 아닌 단어는 `cos × 90 / (유사어 5위의 cos)`로 환산하고 0~99로 자른다. 즉 힌트 유사어 5위가 90%가 되도록 정답마다 보정한다(원본 코사인은 최대 0.5 안팎이라 그대로는 90%가 안 나옴). 그래서 `hints`에는 화면에 쓰지 않는 5번째 유사어도 환산 기준용으로 저장돼 있다.
- **힌트 표시** (`hintList()`/`renderHints()`): 유사어 상위 4개 + 반의어를 게임마다 2번째 또는 3번째 위치에 끼워 넣는다. 처음엔 1개, 유효한 오답마다 1개씩 늘고 종료(정답/포기) 시 모두 공개. 반의어에는 화면 라벨을 붙이지 않는다.
- **난이도** (`pool()`): 정답 후보 풀만 바꾼다. 쉬움=빈도 3,000위 이내이면서 유사어 5위 코사인이 상위 50%, 어려움=하위 40%, 보통=전체. 힌트 개수는 모든 난이도에서 5개.

## 데이터를 바꿀 때

- 정답 후보를 늘리려면 `scripts/antonyms.txt`에 `단어 단어` 쌍을 추가하고 `build_data.py`를 다시 돌린다. 어휘(`vocab.json`의 `words`)에 없는 쌍은 조용히 무시된다.
- 어휘 크기·정제 조건은 `build_data.py` 상단 상수(`SCAN_LINES`, `VOCAB_MAX`)와 `is_noun()`에서 조절한다. 변경하면 `words` 인덱스가 전부 바뀌므로 `vocab.json`과 `vectors.bin`을 함께 재생성해야 한다.
- 브라우저가 예전 `vocab.json`을 캐시하면 새 필드(`ants` 등)가 없어 동작이 어긋난다. 강력 새로고침으로 확인한다.
