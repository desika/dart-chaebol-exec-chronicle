"""DART OpenAPI 인증키. 우선순위: 환경변수 DART_API_KEY → 저장소 루트의 dart_key.txt(.gitignore 대상).
   발급: https://opendart.fss.or.kr (무료, 즉시)"""
import os, pathlib
_f = pathlib.Path(__file__).resolve().parent / "dart_key.txt"
KEY = os.environ.get("DART_API_KEY", "").strip() or (_f.read_text(encoding="utf-8").strip() if _f.exists() else "")
def need_key():
    if not KEY: raise SystemExit("DART 인증키 없음: 환경변수 DART_API_KEY 를 설정하거나 저장소 루트에 dart_key.txt 를 만들 것 (https://opendart.fss.or.kr)")
