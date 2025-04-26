# -*- coding: utf-8 -*-
# config.py - 봇 설정을 위한 변수 저장

# --- 대화(on_message) 관련 설정 ---
MESSAGE_BATCH_DELAY_SECONDS = 8 # 메시지 묶음 처리 대기 시간 (초)

# --- 선톡(proactive DM) 관련 설정 ---
PROACTIVE_DM_INTERVAL_MINUTES = 30 # 선톡 발송 주기 (분)

# --- 호감도 관련 설정 ---
DEFAULT_LIKABILITY_SCORE = 30 # 최초 호감도 점수 (30점으로 변경)
MAX_LIKABILITY_SCORE = 100 # 호감도 최대 점수
MIN_LIKABILITY_SCORE = 0  # 호감도 최소 점수
LIKABILITY_INCREASE_POSITIVE = 2 # 긍정 감정 시 증가 폭
LIKABILITY_DECREASE_NEGATIVE = 1 # 부정 감정 시 감소 폭 (절대값)

# --- 기타 설정 ---
# 예: 요약 기능 사용 시 문장 수 제한 등
SUMMARY_MAX_SENTENCES = 5
# 예: API 호출 시 GenerationConfig 기본값 (길이 제한 등)
# (None 으로 두면 길이 제한 없음)
DEFAULT_GENERATION_CONFIG = None
# 예시: DEFAULT_GENERATION_CONFIG = {"max_output_tokens": 250} # 또는 None
SENTIMENT_GENERATION_CONFIG = {"max_output_tokens": 50, "temperature": 0.2}
SUMMARY_GENERATION_CONFIG = {"max_output_tokens": 200}