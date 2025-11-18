from write_youtube_trend import run_youtube_trend
import os

def test():
    result = run_youtube_trend("크리스마스")

    print("\n📌 첫 항목:")
    print(result[0])

    print("\n📁 이미지 저장 결과:")
    base = os.path.abspath("../../data/images")
    for i in range(1, 6):
        path = os.path.join(base, f"image_{i}.jpg")
        print(f" - image_{i}.jpg: {'✔ 존재' if os.path.exists(path) else '❌ 없음'}")

if __name__ == "__main__":
    test()