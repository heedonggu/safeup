# 세이프업 (SafeUp)

건설·제조 현장용 **영상 매뉴얼 · 안전교육 · 중대재해 의무 관리** 웹앱.
현장에서 찍은 영상을 단계별 매뉴얼로 만들고, AI 자막·번역·음성으로 외국인 근로자까지 교육하고, 이수·점검·보고서를 한곳에서 관리한다.

> 상태: **개발 중(배포 전)**. 이 프로젝트는 개발자 자체 보고가 아니라 외부 평가자(다른 AI 모델)가 기능 체크리스트로 채점해 100%가 나와야 배포한다. 현재 외부 채점 진행 중.

## 주요 기능

| 영역 | 기능 |
|---|---|
| 매뉴얼 제작 | 영상 업로드(H.264 변환), 브라우저 카메라·화면 녹화(마이크 포함), 단계 나누기, 도형·글자 강조, 문서 매뉴얼, PDF·DOCX → AI 매뉴얼 초안, 폴더(다단계) |
| AI | 받아쓰기(faster-whisper) → 용어 사전 → 검수 확정, 업로드 즉시 자동 자막·자동 단계, 100개 이상 언어 번역(로컬 Ollama), AI 음성 읽기(edge-tts), 자막·강조 입힌 영상 내보내기 |
| 개정·승인 | 버전 이력, 단계 개정 이력·되돌리기, 다단계 승인 후 공개, 승인 필수 정책, 개정 시 재이수 |
| 교육 | 개인·부서·사업장 배정, 교육 과정(PDF → 과정 자동 생성, 순서 편집, 진행 리포트), 시청률, 단계 연결 확인 테스트, 서명, 재생 속도, 오프라인 시청 |
| 현장 관리 | 점검표(양식·이상 판정·승인·추이), 스킬 맵, 작업 분석(영상 비교), 위험요인·의견 신고, 도입 관리(목표·계획·회의) |
| 보고서 | 기간·항목 선택 PDF·엑셀(교육·점검·기록·안전·과제·매뉴얼) |
| 중대재해 | 중대재해처벌법 시행령 제4조 9개·제5조② 4개 항목 반기 점검 |
| 보안 | 권한 3단계 + 사용자별 세부 권한, 2단계 인증(TOTP), IP 제한, 접속 기록, 로그인 실패 제한, 백업, 구글·카카오·네이버·회사 SSO(OIDC) |

## 실행

필요: Python 3.11+, ffmpeg/ffprobe, `pip install -r requirements.txt`. 한글 PDF에는 맑은 고딕 또는 나눔 글꼴이 필요하다.

```bash
PYTHONUTF8=1 python build.py      # 공개 페이지 생성(site/)
PYTHONUTF8=1 python server.py     # http://localhost:8800
```

관리자 초기 비밀번호는 첫 실행 때 `data/admin_initial_password.txt`에 생긴다. 로그인 후 지운다.

AI 기능(받아쓰기·번역·문서 초안)은 faster-whisper와 [Ollama](https://ollama.com)(기본 `qwen3:8b`)가 있어야 한다. 없으면 해당 버튼만 오류를 알리고 나머지는 동작한다.

### Docker

```bash
docker compose up -d --build      # 포트 8810, 데이터는 `data` 볼륨
```

HTTPS 뒤에 두고 `COOKIE_SECURE=1`을 켠다. Cloudflare 뒤라면 `CF-Connecting-IP`를 로컬 프록시에서 온 요청일 때만 믿는다.

환경변수: `PORT`, `HOST`, `DATA_DIR`, `SECRET`, `ADMIN_PASSWORD`, `COOKIE_SECURE`, `BASE_URL`, `ASR_PYTHON`, `OLLAMA_URL`, `OLLAMA_MODEL`, `OLLAMA_WARM`, `MAX_UPLOAD_MB`, `SMTP_HOST` 등.

## 시험

```bash
python tests/test_api.py
python tests/test_oauth.py
python tests/test_product.py --no-ai
python tests/test_extra.py --no-ai
```

`--no-ai`를 빼면 받아쓰기·번역까지 실제로 돌린다(Ollama·모델 필요). 문서 AI 시험은 `SAMPLE_PDF=경로`로 PDF를 지정할 때만 돈다.

## 구성

| 파일 | 내용 |
|---|---|
| `server.py` | HTTP 서버, 로그인, 보안 헤더, 라우팅 |
| `product.py`, `more.py`, `extra.py` | 서비스 API |
| `oauth.py` | 소셜·회사 SSO 로그인 |
| `db.py` | SQLite 스키마 |
| `asr_worker.py` | 받아쓰기 실행 |
| `static/` | 화면(바닐라 JS) |
| `data.py`, `build.py` | 공개 페이지 내용과 생성기 |

## 법령 근거

중대재해 처벌 등에 관한 법률 시행령(2025-10-01 시행) 제4조·제5조 원문을 국가법령정보센터 데이터로 대조해 `product.py`의 `LAW`에 넣었다. 앱은 점검과 기록을 돕는 도구이며 법적 충족을 판정하지 않는다.

## 라이선스 · 상업적 이용

**개인·학습·연구·비영리·공공기관 이용은 무료**다. 소스를 보고, 고치고, 내 현장에서 써 봐도 된다.

**상업적 이용과 상품화는 함께 만드는 조건으로만 열려 있다.** 이 앱이나 이 아이디어(영상 매뉴얼 + AI 다국어 안전교육 + 중대재해 의무 관리 결합)로 돈을 벌거나 서비스·제품을 내려면 다음 중 하나를 먼저 한다.

1. **협업 제안** — [협업 제안 이슈](../../issues/new?template=collaboration.yml)를 연다. 회사, 쓰려는 방식, 함께 할 수 있는 부분을 적는다.
2. **기여** — 기능·수정·번역·현장 자료로 의미 있는 기여를 하고, 협업 제안 이슈에서 상업 이용 조건을 합의한다.

합의 없는 상업적 이용·재판매·SaaS 제공·상품화는 허락하지 않는다. 라이선스는 [PolyForm Noncommercial 1.0.0](LICENSE)(비상업 소스 공개, OSI 오픈소스 아님), 상업 허락 조건은 [COMMERCIAL.md](COMMERCIAL.md).

## 기여

이슈와 PR 모두 환영한다. [CONTRIBUTING.md](CONTRIBUTING.md)를 먼저 읽는다. 올라온 이슈는 개발 방향(현장 안전교육·의무 관리의 실제 사용성)에 맞는지 검토해 반영 여부와 결과를 이슈에 답한다.

---

**English summary** — SafeUp is a video-manual, safety-training and compliance web app for construction sites (Python stdlib server + SQLite + vanilla JS, local AI via faster-whisper and Ollama). Free for personal, educational, research and non-profit use. **Commercial use or productization requires a collaboration agreement or a meaningful contribution** — open a [collaboration proposal issue](../../issues/new?template=collaboration.yml). License: PolyForm Noncommercial 1.0.0 ([LICENSE](LICENSE)); commercial terms in [COMMERCIAL.md](COMMERCIAL.md).
