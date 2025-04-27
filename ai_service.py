# -*- coding: utf-8 -*-
# ai_service.py - Gemini API 호출 관련 함수

import google.generativeai.types as genai_types
import re
import traceback

import config
import prompts

async def generate_response(model, user_message, current_history, current_likability):
    """사용자 메시지에 대한 응답 생성"""
    print("DEBUG: generate_response - 1단계: 전체 응답 생성 시도...")
    
    # API 요청을 위한 히스토리 준비
    history_for_api = current_history.copy()
    history_for_api.append({'role': 'user', 'parts': [user_message]})
    
    # 호감도 컨텍스트 추가
    likability_percent = f"{current_likability}%"
    likability_context_prompt = f"(시스템 컨텍스트: 참고로 현재 이 사용자와 나의 호감도는 {likability_percent} 야. 이 호감도 %와 나의 역할 설정(System Instruction)에 명시된 기준에 따라 말투와 태도를 엄격하게 조절해서 응답해야 해. 호감도 점수 자체를 언급하지는 마.)"
    history_for_api.append({'role': 'user', 'parts': [likability_context_prompt]})
    
    try:
        # Gemini API 호출
        response = await model.generate_content_async(
            history_for_api,
            generation_config=None  # 또는 config에서 가져온 설정
        )
        
        if not (response and response.text):
            raise Exception("Initial generation failed or blocked")
        
        bot_response_text_full = response.text.strip()
        print(f"DEBUG: generate_response - 1단계 생성 전체 응답: {bot_response_text_full[:100]}...")
        
        # 2단계: 길이 확인 및 필요시 요약 (3문장 초과 시)
        sentences = re.split(r'(?<=[.?!])\s+', bot_response_text_full)
        if len(sentences) > 3:
            print(f"DEBUG: 답변이 {len(sentences)} 문장으로 길어서 요약 시도...")
            summarized_text = await summarize_text(model, bot_response_text_full)
            if summarized_text:
                final_text_to_send = summarized_text
            else:
                print("경고: 요약 실패. 원본 답변의 첫 3문장 사용.")
                final_text_to_send = " ".join(sentences[:3])
        else:
            print("DEBUG: 답변이 3문장 이하이므로 원본 사용.")
            final_text_to_send = bot_response_text_full
        
        return bot_response_text_full, final_text_to_send
        
    except Exception as e:
        print(f"오류: 응답 생성 중 예외 발생 - {e}")
        traceback.print_exc()
        return "미안, 지금은 말을 잘 못하겠어... 😥", "미안, 지금은 말을 잘 못하겠어... 😥"

async def calculate_likability(model, current_score, message_content):
    """메시지 감정 분석을 통한 호감도 계산"""
    print(f"DEBUG: calculate_likability 호출됨 - 현재 점수: {current_score}, 메시지: '{message_content[:20]}...'")
    new_score = current_score
    
    try:
        generation_config_sentiment = genai_types.GenerationConfig(**config.SENTIMENT_GENERATION_CONFIG)
        sentiment_prompt = prompts.SENTIMENT_ANALYSIS_PROMPT_TEMPLATE.format(user_message=message_content)
        print(f"DEBUG: 감성 분석 프롬프트 전송 시도")
        
        sentiment_response = await model.generate_content_async(
            sentiment_prompt, 
            generation_config=generation_config_sentiment
        )
        
        if sentiment_response and sentiment_response.text:
            sentiment = sentiment_response.text.strip().upper()
            print(f"DEBUG: 감성 분석 결과: {sentiment}")
            
            if sentiment == "POSITIVE":
                new_score += config.LIKABILITY_INCREASE_POSITIVE
                print(f"DEBUG: 호감도 증가! (+{config.LIKABILITY_INCREASE_POSITIVE})")
            elif sentiment == "NEGATIVE":
                new_score -= config.LIKABILITY_DECREASE_NEGATIVE
                print(f"DEBUG: 호감도 감소! (-{config.LIKABILITY_DECREASE_NEGATIVE})")
            else:
                print(f"DEBUG: 호감도 변경 없음 (감성: {sentiment})")
        else:
            print(f"경고: 감성 분석 API 응답 비었음. 호감도 변경 없음.")
    except Exception as e:
        print(f"오류: 감성 분석 API 호출 중 오류 발생: {e}")
        traceback.print_exc()
    
    # 호감도 범위 제한
    new_score = max(config.MIN_LIKABILITY_SCORE, min(config.MAX_LIKABILITY_SCORE, new_score))
    print(f"DEBUG: calculate_likability 최종 결과 - 새 점수: {new_score}")
    
    return new_score

async def summarize_text(model, text_to_summarize):
    """긴 텍스트 요약"""
    print(f"DEBUG: summarize_text 호출됨 - 요약 대상 (시작): '{text_to_summarize[:50]}...'")
    
    try:
        summary_prompt = prompts.SUMMARIZE_PROMPT_TEMPLATE.format(text_to_summarize=text_to_summarize)
        generation_config_summary = genai_types.GenerationConfig(**config.SUMMARY_GENERATION_CONFIG)
        
        summary_response = await model.generate_content_async(
            summary_prompt, 
            generation_config=generation_config_summary
        )
        
        if summary_response and summary_response.text:
            summarized_text = summary_response.text.strip()
            print(f"DEBUG: 요약 성공 - 요약 결과: {summarized_text}")
            return summarized_text
        else:
            print(f"경고: 요약 API 응답 비었거나 문제 있음.")
            return None
    except Exception as e:
        print(f"오류: 요약 API 호출 중 오류 발생: {e}")
        traceback.print_exc()
        return None

async def generate_proactive_message(model, user_id, user_display_name):
    """선톡 메시지 생성"""
    # 사용자 데이터 로드
    current_history, current_likability = load_user_data(user_id)
    print(f"DEBUG: 선톡 - 로드된 기록 (총 {len(current_history)} 턴), 호감도: {current_likability}")
    
    # 프롬프트 준비
    proactive_instruction = prompts.PROACTIVE_DM_PROMPT_TEMPLATE.format(user_display_name=user_display_name)
    history_with_instruction = current_history.copy()
    history_with_instruction.append({'role': 'user', 'parts': [proactive_instruction]})
    
    try:
        # Gemini API 호출
        generation_config = genai_types.GenerationConfig(**config.DEFAULT_GENERATION_CONFIG) if config.DEFAULT_GENERATION_CONFIG else None
        response = await model.generate_content_async(
            history_with_instruction, 
            generation_config=generation_config
        )
        
        if response and response.text:
            generated_text = response.text.strip()
            print(f"Gemini 생성 메시지 (선톡, 전체): {generated_text[:100]}...")
            
            # 요약 필요 여부 확인
            sentences = re.split(r'(?<=[.?!])\s+', generated_text)
            if len(sentences) > config.SUMMARY_MAX_SENTENCES:
                print(f"DEBUG: 선톡 - 답변이 {len(sentences)} 문장으로 길어서 요약 시도...")
                summarized_text = await summarize_text(model, generated_text)
                if summarized_text:
                    final_text = summarized_text
                else:
                    print(f"경고: 선톡 요약 실패. 원본 첫 {config.SUMMARY_MAX_SENTENCES} 문장 사용.")
                    final_text = " ".join(sentences[:config.SUMMARY_MAX_SENTENCES])
            else:
                final_text = generated_text
            
            return generated_text, final_text  # 원본 텍스트와 최종 텍스트 반환
        else:
            print(f"경고: Gemini 응답 비었거나 차단됨. 기본 메시지 사용.")
            return None, None
    except Exception as e:
        print(f"오류: Gemini 메시지 생성 중 오류 발생 - {e}")
        traceback.print_exc()
        return None, None

# database.py 임포트는 함수 내부에서만 사용하여 순환 참조 방지
from database import load_user_data, save_user_data