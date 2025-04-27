# -*- coding: utf-8 -*-
# utils.py - 유틸리티 함수들

import asyncio
import random
import re
import traceback
from typing import List

import discord

import config
import prompts
from database import get_all_user_ids, load_user_data, save_user_data
from ai_service import generate_proactive_message

async def send_proactive_message(bot):
    """선톡 보내는 함수 - 선택된 사용자에게 자동 메시지 발송"""
    print("DEBUG: 선톡 작업 실행됨.")
    
    # 1. DB에서 모든 상호작용한 사용자 ID 목록 가져오기
    all_user_ids = get_all_user_ids()

    if not all_user_ids:
        print("DEBUG: 선톡 - 대화 기록이 있는 사용자가 없어 선톡을 건너뜁니다.")
        return

    # 2. 선톡 보낼 대상 랜덤 선택
    try:
        chosen_user_id = random.choice(all_user_ids)
        print(f"DEBUG: 선톡 - 총 {len(all_user_ids)}명 중 {chosen_user_id} 에게 선톡 시도.")
    except IndexError:
        print("DEBUG: 선톡 - 사용자 ID 목록이 비어있어 대상을 선택할 수 없음.")
        return

    # 3. 선택된 사용자 정보 가져오기 및 선톡 보내기
    try:
        user = await bot.fetch_user(chosen_user_id)
        if not user:
            print(f"경고: 선톡 대상 사용자를 찾을 수 없습니다 (ID: {chosen_user_id})")
            return
            
        print(f"선톡 대상 확인: {user.name} ({chosen_user_id})")
        
        # 사용자 데이터 로드
        target_user_history, target_user_likability = load_user_data(chosen_user_id)
        
        # Gemini 메시지 생성
        message_to_send_full, final_text_to_send = await generate_proactive_message(
            bot.model, chosen_user_id, user.display_name)
        
        # 메시지 생성 실패 시 기본 메시지 사용
        if not message_to_send_full:
            message_to_send_full = random.choice(prompts.PROACTIVE_DM_FALLBACKS)
            final_text_to_send = message_to_send_full
        
        # DM 발송
        print(f"선톡 시도 -> User ID: {chosen_user_id}, 메시지 (최종): {final_text_to_send[:100]}...")
        if final_text_to_send:
            final_sentences = re.split(r'(?<=[.?!])\s+', final_text_to_send)
            for sentence in final_sentences:
                sentence = sentence.strip()
                if sentence:
                    await user.send(sentence)
                    await asyncio.sleep(random.uniform(1.0, 2.0))
            
            print(f"선톡 성공 (분할 전송 완료) -> User ID: {chosen_user_id}")
            
            # DB에 저장
            final_history_to_save = target_user_history
            final_history_to_save.append({'role': 'model', 'parts': [message_to_send_full]})
            save_user_data(chosen_user_id, final_history_to_save, target_user_likability)
            print(f"선톡 내용(원본) DB 저장 완료 -> User ID: {chosen_user_id}, 호감도: {target_user_likability}")
        else:
            print(f"경고: 최종적으로 보낼 메시지가 없습니다.")

    except discord.NotFound:
        print(f"오류: 선톡 대상 사용자를 찾을 수 없습니다 (ID: {chosen_user_id})")
    except discord.Forbidden:
        print(f"오류: 선톡 대상 사용자에게 DM을 보낼 권한이 없습니다 (ID: {chosen_user_id})")
    except Exception as e:
        print(f"선톡 대상 처리 중 예외 발생 (User ID: {chosen_user_id}): {e}")
        traceback.print_exc()