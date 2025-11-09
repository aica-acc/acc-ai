# -*- coding: utf-8 -*-
"""
vertical_1008_3024_make_banner_from_prompt.py
- (width/height/prompt[+옵션]) JSON → Dreamina 3.1 호출 → out/ 저장
"""

import os, re, json, time
from pathlib import Path

try:
    import replicate
except Exception as e:
    raise SystemExit("[에러] 'replicate' 모듈이 없습니다.  `pip install replicate`") from e
try:
    import requests
except Exception as e:
    raise SystemExit("[에러] 'requests' 모듈이 없습니다.  `pip install requests`") from e

SCRIPT_DIR = Path(__file__).resolve().parent
OUT_DIR = SCRIPT_DIR / "out"

try:
    from dotenv import load_dotenv, find_dotenv
except Exception:
    load_dotenv = None
    find_dotenv = None

DEFAULT_MODEL = "bytedance/dreamina-3.1"
MIN_WH = 512
MAX_WH = 3024

def _load_env():
    if load_dotenv and find_dotenv:
        env = find_dotenv(usecwd=True)
        if env: load_dotenv(env, override=False)
        else:
            local = SCRIPT_DIR / ".env"
            if local.exists(): load_dotenv(local, override=False)

def _require_token():
    tok = os.getenv("REPLICATE_API_TOKEN")
    if tok: return tok
    _load_env()
    tok = os.getenv("REPLICATE_API_TOKEN")
    if tok: return tok
    raise RuntimeError("REPLICATE_API_TOKEN을 찾을 수 없습니다(.env).")

def _model_slug():
    m = os.getenv("REPLICATE_MODEL")
    if not m:
        _load_env(); m = os.getenv("REPLICATE_MODEL")
    return m.strip().strip('"').strip("'") if m else DEFAULT_MODEL

def ask_path(msg: str) -> Path:
    while True:
        raw = input(msg).strip().strip('"')
        p = Path(raw)
        if p.exists() and p.is_file(): return p
        print("[안내] 경로가 올바르지 않습니다. 다시 입력하세요.")

def load_job(job_path: Path) -> dict:
    data = json.loads(job_path.read_text(encoding="utf-8"))
    for k in ("width","height","prompt"):
        if k not in data: raise ValueError(f"[에러] JSON에 '{k}' 키가 없습니다.")
    return data

def slug_from_prompt(prompt: str) -> str:
    m = re.search(r'TITLE\s*=\s*([^,;|\n]+)', prompt, flags=re.IGNORECASE)
    if not m:
        m = re.search(r'TITLE\s*:\s*(?:"([^"]+)"|([^;,\n]+))', prompt, flags=re.IGNORECASE)
    base = (m.group(1) or m.group(2)).strip() if m else "banner"
    base = re.sub(r"[^\w\s\uAC00-\uD7A3-]", "", base).strip()
    base = re.sub(r"\s+", "_", base)
    return base[:50] if base else "banner"

def _clamp(v:int) -> int: return max(MIN_WH, min(MAX_WH, int(v)))

def run_dreamina(job: dict):
    os.environ["REPLICATE_API_TOKEN"] = _require_token()
    model = _model_slug()

    w, h = _clamp(job["width"]), _clamp(job["height"])
    if (w,h) != (1008,3024):
        print(f"[경고] 입력 해상도 {w}x{h}가 기본 1008x3024와 다릅니다. (aspect_ratio='custom'에서만 적용)")

    inputs = {
        "prompt": job["prompt"],
        "aspect_ratio": job.get("aspect_ratio","custom"),
        "width": w, "height": h,
    }
    for key in ("resolution","seed","use_pre_llm"):
        if key in job: inputs[key] = job[key]

    print(f"[info] Replicate.run -> {model} {inputs.get('aspect_ratio')} ({w}x{h})")
    return replicate.run(model, input=inputs)

def download_and_save(urls, out_dir: Path, base_name: str):
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = []; ts = time.strftime("%Y%m%d_%H%M%S")
    for i,url in enumerate(urls if isinstance(urls,list) else [urls],1):
        r = requests.get(url, timeout=120); r.raise_for_status()
        ext = ".jpg" if "jpeg" in r.headers.get("Content-Type","") else ".png"
        out_path = out_dir / f"{base_name}_dreamina_{ts}_{i}{ext}"
        out_path.write_bytes(r.content); saved.append(out_path)
    return saved

def main():
    print("=== Dreamina 3.1 배너 생성기 (prompt JSON -> 이미지, 1008x3024 기본) ===")
    job_path = ask_path("1) job JSON 경로(width/height/prompt[+옵션]): ")
    try:
        job = load_job(job_path)
    except Exception as e:
        print(e); return

    print(f"[info] width: {job['width']}, height: {job['height']}")
    pv = job["prompt"]; print(f"[info] prompt 미리보기: {pv[:180]}{'...' if len(pv)>180 else ''}")

    base_name = slug_from_prompt(job["prompt"])
    try:
        output = run_dreamina(job)
    except Exception as e:
        print(f"[실패] Dreamina 실행 중 오류: {e}"); return
    if not output:
        print("[실패] Dreamina 응답이 비어 있습니다."); return

    saved = download_and_save(output, OUT_DIR, base_name)
    print("\n[완료] 저장된 파일:")
    for p in saved: print(" -", p.resolve())

if __name__ == "__main__":
    main()
