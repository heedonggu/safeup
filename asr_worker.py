"""받아쓰기. faster-whisper 가 있는 파이썬(ASR_PYTHON)으로 따로 실행한다. 입력: wav 경로 [언어]. 출력: JSON 구간 목록."""
import json
import sys

from faster_whisper import WhisperModel


def main(path, language='ko'):
    try:
        model = WhisperModel('medium', device='cpu', compute_type='int8', cpu_threads=4, local_files_only=True)
    except Exception:  # 새 서버: 처음 한 번 모델을 받는다
        model = WhisperModel('medium', device='cpu', compute_type='int8', cpu_threads=4)
    segs, _ = model.transcribe(path, language=language, vad_filter=True, beam_size=5)
    json.dump([{'start': round(s.start, 2), 'end': round(s.end, 2), 'text': s.text.strip()} for s in segs if s.text.strip()], sys.stdout, ensure_ascii=False)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main(*sys.argv[1:3])
