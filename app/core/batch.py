"""
생성 결과를 요청 단위(batch) 폴더에 저장하고, 같은 요청을 다시 받으면 이미 만든 것은 다시 만들지 않는다 (트러블슈팅 #31).

예전에는 모든 회원·프로젝트의 결과가 {type}/ 한 폴더에 쌓였고, 백엔드는 "그 폴더에 4장 이상 있으면 저장 실패분"
으로 보고 재사용했다. 그러면 다른 프로젝트가 남긴 이미지가 섞일 수 있다.

  batch      : 백엔드가 정하는 요청 키 (회원_프로젝트). {type}/{batch}/ 에 저장
  result_name: {type}_{순번}_{프롬프트 해시}.png — 같은 순번·같은 프롬프트면 같은 파일이라 다시 요청해도 비용이 들지 않고,
               프롬프트가 바뀌면 다른 파일이 된다
"""
import hashlib
import re
from pathlib import Path
from typing import Optional

_BATCH = re.compile(r"^[\w-]{1,64}$")


def batch_dir(base: Path, batch: Optional[str]) -> Path:
    if batch is None:
        d = Path(base)
    elif _BATCH.match(batch):
        d = Path(base) / batch
    else:
        raise ValueError(f"invalid batch: {batch!r}")
    d.mkdir(parents=True, exist_ok=True)
    return d


def result_name(kind: str, index: int, prompt: str) -> str:
    digest = hashlib.sha1((prompt or "").encode("utf-8")).hexdigest()[:10]
    return f"{kind}_{index}_{digest}.png"
