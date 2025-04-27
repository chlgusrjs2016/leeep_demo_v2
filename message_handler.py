# -*- coding: utf-8 -*-
# message_handler.py - 메시지 처리 관련 함수

import asyncio
import random
import re
import traceback
from typing import Dict, List

import discord

from database import load_user_data, save_user_data
import config
from ai_service import generate_response, calculate_likability, summarize_text

# 메시지 버퍼 및 타이머 관리용 전역 변수
user_message_buffers: Dict[int, List[discord.Message]] = {}
user_timer_tasks: Dict[int, asyncio.Task] = {}

async def process_message_batch(user_id: int, model, bot_user):
    """타이머 만료 시 메시지 묶음 처리 함수"""
    global user_message_buffers, user_timer_tasks
    print(f"DEBUG: process_message_batch 시작 - 사용자 ID: {user_id}")
    
    if user_id in user_timer_tasks:
        del user_timer_tasks[user_id]
        print(f"DEBUG: process_message_batch - 타이머 작업 제거됨")

    if user_id not in user_message_buffers:
        print(f"DEBUG: process_message_batch - 사용자 ID {user_id} 버퍼가 이미 비어있음.")
        return
        
    messages_to_process = user_message_buffers.pop(user_id)
    print(f"DEBUG: process_message_batch - 버퍼 메시지 가져옴 (개수: {len(messages_to_process)})")
    
    if not messages_to_process:
        print(f"DEBUG: 처리할 메시지 없음")
        return

    last_message = messages_to_process[-1]
    channel = last_message.channel
    combined_message_content = "\n".join([msg.content for msg in messages_to_process])
    print(f"DEBUG: process_message_batch - 합쳐진 메시지: '{combined_message_content}'")

    current_history, current_likability = load_user_data(user_id)
    print(f"DEBUG: process_message_batch - 로드됨 -> 기록: {len(current_history)}턴, 호감도: {current_likability}")

    async with channel.typing():
        try:
            # 대화 처리 및 응답 생성
            bot_response_text_full, final_text_to_send = await generate_response(
                model, combined_message_content, current_history, current_likability)
            
            # 성공 시 호감도 계산
            new_likability = await calculate_likability(model, current_likability, combined_message_content)
            
            # 대화 기록에 추가
            current_history.append({'role': 'user', 'parts': [combined_message_content]})
            current_history.append({'role': 'model', 'parts': [bot_response_text_full]})  # 전체 응답 저장
            
            # 대화 기록 관리 (최대 길이 제한)
            current_history = trim_history(current_history)
            
            # DB에 저장
            save_user_data(user_id, current_history, new_likability)
            print(f"DEBUG: 대화 저장 완료 (총 {len(current_history)} 턴), 새 호감도: {new_likability}")

            # 최종 텍스트 분할 전송
            print(f"DEBUG: process_message_batch - 최종 전송할 텍스트: {final_text_to_send[:100]}...")
            final_sentences = re.split(r'(?<=[.?!])\s+', final_text_to_send)
            for sentence in final_sentences:
                sentence = sentence.strip()
                if sentence:
                    await channel.send(sentence)
                    await asyncio.sleep(random.uniform(1.0, 2.0))

        except Exception as e:
            print(f"오류: User {user_id} 메시지 처리(요약 포함) 중 - {e}")
            traceback.print_exc()
            if not 'final_text_to_send' in locals() or not final_text_to_send:
                await channel.send("미안, 방금 하신 말씀들을 처리하는 데 문제가 생겼어요. 😥")

    if user_id in user_timer_tasks:
        del user_timer_tasks[user_id]
        print(f"DEBUG: process_message_batch - 타이머 작업 최종 제거됨")

def trim_history(history_list, max_turns=10):
    """대화 이력이 너무 길면 최근 N턴만 유지합니다"""
    if len(history_list) > max_turns * 2:  # 사용자/봇 메시지 쌍이므로 *2
        return history_list[-max_turns*2:]
    return history_list

async def handle_new_message(message, bot):
    """새 메시지 처리 - 버퍼링 및 타이머 설정"""
    global user_message_buffers, user_timer_tasks
    
    user_id = message.author.id
    print(f"[DM 수신] {message.author.name}: {message.content}")
    
    if user_id not in user_message_buffers:
        user_message_buffers[user_id] = []
    
    user_message_buffers[user_id].append(message)
    print(f"DEBUG: 메시지 버퍼 추가됨 - 사용자 ID: {user_id}, 현재 버퍼 크기: {len(user_message_buffers[user_id])}")
    
    if user_id in user_timer_tasks:
        existing_task = user_timer_tasks[user_id]
        if not existing_task.done():
            print(f"DEBUG: 기존 타이머 취소 시도 - 사용자 ID: {user_id}")
            existing_task.cancel()

    async def delayed_process(uid):
        try:
            await asyncio.sleep(config.MESSAGE_BATCH_DELAY_SECONDS)
            print(f"DEBUG: {config.MESSAGE_BATCH_DELAY_SECONDS}초 타이머 만료 - 사용자 ID: {uid}, 처리 함수 호출 시도.")
            await process_message_batch(uid, bot.model, bot.user)
        except asyncio.CancelledError:
            print(f"DEBUG: 타이머 작업 정상 취소됨 (새 메시지 수신) - 사용자 ID: {uid}")
        except Exception as e:
            print(f"오류: delayed_process 작업 중 예외 발생 - 사용자 ID: {uid}, 오류: {e}")
            traceback.print_exc()
            if uid in user_timer_tasks:
                del user_timer_tasks[uid]
                print(f"DEBUG: 오류 발생 후 타이머 작업 정리됨 - 사용자 ID: {uid}")
            if uid in user_message_buffers:
                del user_message_buffers[uid]
                print(f"DEBUG: 오류 발생 후 메시지 버퍼 정리됨 - 사용자 ID: {uid}")

    print(f"DEBUG: 새 타이머 시작 ({config.MESSAGE_BATCH_DELAY_SECONDS}초) - 사용자 ID: {user_id}")
    user_timer_tasks[user_id] = asyncio.create_task(delayed_process(user_id))