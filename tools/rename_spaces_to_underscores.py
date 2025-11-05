# tools/rename_spaces_to_underscores.py
from pathlib import Path
import os
import unicodedata
import re

ROOT = Path("홍보물")

def to_underscores(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    s = re.sub(r"\s+", "_", s).strip("_")
    return s

def rename_tree(root: Path):
    # 깊은 경로부터 파일 → 디렉터리 순으로 안전하게 이름 변경
    for p in sorted(root.rglob("*"), key=lambda x: (x.is_dir(), -len(str(x)))):
        new_name = to_underscores(p.name)
        if new_name != p.name:
            target = p.with_name(new_name)
            try:
                os.rename(p, target)
            except OSError:
                # Windows에서 열려있는 파일/폴더는 실패할 수 있음
                print(f"[WARN] rename failed: {p} -> {target}")

if __name__ == "__main__":
    if ROOT.exists():
        rename_tree(ROOT)
        print("Done.")
    else:
        print(f"Not found: {ROOT}")
