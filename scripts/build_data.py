"""fastText 한국어 벡터에서 게임 데이터(web/data/*)를 만든다.

사용법: .venv/bin/python scripts/build_data.py
- 상위 빈도 단어를 스트리밍으로 읽고(전체 1.2GB 다운로드 불필요), 한글 명사만 남긴다.
- vectors.bin : 단어별 L2 정규화 벡터(int8, DIM차원)
- vocab.json  : {words, answers(2글자 정답 후보 인덱스), hints(정답별 상위 5개 인덱스와 코사인)}
"""
import gzip, json, re, sys, urllib.request
from pathlib import Path
import numpy as np
from kiwipiepy import Kiwi

URL = "https://dl.fbaipublicfiles.com/fasttext/vectors-crawl/cc.ko.300.vec.gz"
SCAN_LINES = 300_000   # 빈도순 상위 몇 줄까지 읽을지
VOCAB_MAX = 40_000     # 추측 가능한 단어 수
ANSWER_POOL = 6_000    # 정답은 이 순위 안의 2글자 명사에서만
N_HINTS = 5
OUT = Path(__file__).resolve().parent.parent / "web" / "data"
HANGUL = re.compile(r"^[가-힣]{2,6}$")

kiwi = Kiwi()

def is_noun(w):
    toks = kiwi.tokenize(w)
    return len(toks) == 1 and toks[0].tag == "NNG" and not toks[0].oov and toks[0].form == w

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    words, vecs = [], []
    print("스트리밍 시작...", flush=True)
    with urllib.request.urlopen(URL) as r, gzip.open(r, "rt", encoding="utf-8") as f:
        f.readline()  # 헤더
        for i, line in enumerate(f):
            if i >= SCAN_LINES or len(words) >= VOCAB_MAX:
                break
            parts = line.rstrip().split(" ")
            w = parts[0]
            if not HANGUL.match(w) or not is_noun(w):
                continue
            words.append(w)
            vecs.append(np.asarray(parts[1:], dtype=np.float32))
            if len(words) % 5000 == 0:
                print(f"  {len(words)}개 (줄 {i})", flush=True)
    V = np.stack(vecs)
    V /= np.linalg.norm(V, axis=1, keepdims=True)
    print("어휘", len(words))

    # 반의어 사전: 어휘에 둘 다 있는 쌍만 사용(양방향)
    idx = {w: i for i, w in enumerate(words)}
    ant_map = {}
    for line in (Path(__file__).parent / "antonyms.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        x, y = line.split()
        if x in idx and y in idx:
            ant_map.setdefault(idx[x], set()).add(idx[y])
            ant_map.setdefault(idx[y], set()).add(idx[x])

    # 정답은 반의어가 있는 2글자 단어로 한정한다(목록을 직접 골랐으므로 빈도 제한은 두지 않음).
    answers = [i for i in sorted(ant_map) if len(words[i]) == 2]
    hints, ants, kept = {}, {}, []
    for a in answers:
        sims = V @ V[a]
        # 반의어가 여러 개면 코사인이 가장 높은(가장 익숙한) 것을 쓴다.
        ant = max(ant_map[a], key=lambda j: sims[j])
        order = np.argsort(-sims)
        picked = []
        for j in order:
            if j == a or j == ant:
                continue
            w = words[j]
            if words[a] in w or w in words[a]:   # 같은 글자를 포함하는 뻔한 힌트 제외
                continue
            picked.append(int(j))
            if len(picked) == N_HINTS:
                break
        kept.append(a)
        hints[a] = [[j, round(float(sims[j]), 4)] for j in picked]
        ants[a] = [int(ant), round(float(sims[ant]), 4)]
    print("정답 후보(반의어 있음)", len(kept), "/ 반의어 쌍 사용", sum(len(v) for v in ant_map.values()) // 2)

    q = np.clip(np.round(V * 127), -127, 127).astype(np.int8)
    (OUT / "vectors.bin").write_bytes(q.tobytes())
    (OUT / "vocab.json").write_text(
        json.dumps({"dim": int(V.shape[1]), "words": words, "answers": kept,
                    "hints": {str(k): v for k, v in hints.items()},
                    "ants": {str(k): v for k, v in ants.items()}},
                   ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("저장 완료", OUT)

if __name__ == "__main__":
    sys.exit(main())
