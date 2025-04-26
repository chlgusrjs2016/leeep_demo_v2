# -*- coding: utf-8 -*-
# bot.py

import discord
from discord.ext import commands, tasks
import os
from dotenv import load_dotenv
import google.generativeai as genai
import google.generativeai.types as genai_types # GenerationConfig 사용 시 필요할 수 있음
import random
import asyncio # Cog 로딩 위해 필요
import traceback # 오류 상세 출력을 위해 추가
from typing import Dict, List # 타입 힌팅 위해 추가
import re # 문장 분리를 위해 re 임포트

# --- 다른 .py 파일에서 함수 및 변수 가져오기 ---
try:
    from database import init_db, load_user_data, save_user_data
    import prompts
    print("DEBUG: database.py 및 prompts.py 임포트 성공.")
except ImportError as e:
    print(f"오류: database.py 또는 prompts.py 임포트 실패! 파일이 존재하고 문법 오류가 없는지 확인하세요. 오류: {e}")
    exit()
# -------------------------------------------

# --- .env 로드 및 변수 설정 ---
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GOOGLE_API_KEY')
DISCORD_APP_ID = os.getenv('DISCORD_APP_ID')
TARGET_USER_ID_STR = os.getenv('TARGET_USER_ID')

# --- 비밀 정보 로드 확인 ---
if not DISCORD_TOKEN: print("오류: .env 파일에 DISCORD_TOKEN을 설정해주세요."); exit()
if not GEMINI_API_KEY: print("오류: .env 파일에 GOOGLE_API_KEY를 설정해주세요."); exit()
if not DISCORD_APP_ID: print("오류: .env 파일에 DISCORD_APP_ID를 설정해주세요."); exit()
if not TARGET_USER_ID_STR: print("오류: .env 파일에 TARGET_USER_ID를 설정해주세요."); exit()

try:
    TARGET_USER_ID = int(TARGET_USER_ID_STR)
    print(f"환경 변수 로드 완료. 선톡 대상 사용자 ID: {TARGET_USER_ID}")
except ValueError:
    print(f"오류: .env 파일의 TARGET_USER_ID ('{TARGET_USER_ID_STR}')가 유효한 숫자가 아닙니다.")
    exit()

# --- Gemini API 설정 및 모델 초기화 ---
try:
    genai.configure(api_key=GEMINI_API_KEY)
    print(f"시스템 프롬프트 로드됨 (일부): {prompts.SYSTEM_INSTRUCTION[:100]}...")
    SELECTED_MODEL = 'gemini-1.5-flash-latest'
    # SELECTED_MODEL = 'gemini-1.5-pro-latest' # Pro 모델 사용 시

    model = genai.GenerativeModel(
        SELECTED_MODEL,
        system_instruction=prompts.SYSTEM_INSTRUCTION
    )
    print(f"Gemini API 설정 및 모델({model.model_name}) 초기화 완료.")
except Exception as e: print(f"Gemini API 설정 또는 모델 초기화 중 오류 발생: {e}"); exit()


# --- Discord 봇 설정 ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)


# --- 메시지 버퍼 및 타이머 관리용 전역 변수 ---
user_message_buffers: Dict[int, List[discord.Message]] = {}
user_timer_tasks: Dict[int, asyncio.Task] = {}
# ----------------------------------------------------


# --- 호감도 계산 함수 (비동기) ---
async def calculate_likability(model, current_score, message_content):
    """ Gemini를 사용하여 메시지 감성을 분석하고 새로운 호감도를 계산합니다. """
    print(f"DEBUG: calculate_likability 호출됨 - 현재 점수: {current_score}, 메시지: '{message_content[:20]}...'")
    new_score = current_score
    try:
        # Generation Config (감성 분석용 - 짧은 답변 유도)
        # genai_types 임포트 필요
        generation_config_sentiment = genai_types.GenerationConfig(max_output_tokens=50, temperature=0.2)
        sentiment_prompt = prompts.SENTIMENT_ANALYSIS_PROMPT_TEMPLATE.format(user_message=message_content)
        print(f"DEBUG: 감성 분석 프롬프트 전송 시도")
        sentiment_response = await model.generate_content_async(
            sentiment_prompt,
            generation_config=generation_config_sentiment # 생성 설정 전달
        )
        if sentiment_response and sentiment_response.text:
            sentiment = sentiment_response.text.strip().upper()
            print(f"DEBUG: 감성 분석 결과: {sentiment}")
            if sentiment == "POSITIVE": new_score += 2; print(f"DEBUG: 호감도 증가! (+2)")
            elif sentiment == "NEGATIVE": new_score -= 1; print(f"DEBUG: 호감도 감소! (-1)")
            else: print(f"DEBUG: 호감도 변경 없음 (감성: {sentiment})")
        else: print(f"경고: 감성 분석 API 응답 비었음. 호감도 변경 없음.")
    except Exception as e: print(f"오류: 감성 분석 API 호출 중 오류 발생: {e}. 호감도 변경 없음.")
    new_score = max(0, min(100, new_score)) # 예: 0~100점 제한
    print(f"DEBUG: calculate_likability 최종 결과 - 새 점수: {new_score}")
    return new_score


# --- 타이머 만료 시 메시지 묶음 처리 함수 ---
async def process_message_batch(user_id: int):
    global user_message_buffers, user_timer_tasks # 전역 변수 사용 명시
    print(f"DEBUG: process_message_batch 시작 - 사용자 ID: {user_id}")
    if user_id in user_timer_tasks: del user_timer_tasks[user_id]; print(f"DEBUG: process_message_batch - 타이머 작업 제거됨")

    if user_id in user_message_buffers:
        messages_to_process = user_message_buffers.pop(user_id)
        print(f"DEBUG: process_message_batch - 버퍼 메시지 가져옴 (개수: {len(messages_to_process)})")
        if not messages_to_process: print(f"DEBUG: 처리할 메시지 없음"); return

        last_message = messages_to_process[-1]
        author = last_message.author; channel = last_message.channel
        combined_message_content = "\n".join([msg.content for msg in messages_to_process])
        print(f"DEBUG: process_message_batch - 합쳐진 메시지: '{combined_message_content}'")

        current_history, current_likability = load_user_data(user_id)
        print(f"DEBUG: process_message_batch - 로드됨 -> 기록: {len(current_history)}턴, 호감도: {current_likability}")

        history_for_api = current_history.copy()
        history_for_api.append({'role': 'user', 'parts': [combined_message_content]})
        likability_percent = f"{current_likability}%"
        likability_context_prompt = f"(시스템 컨텍스트: 참고로 현재 이 사용자와 나의 호감도는 {likability_percent} 야. 이 호감도 %와 나의 역할 설정(System Instruction)에 명시된 기준에 따라 말투와 태도를 엄격하게 조절해서 응답해야 해. 호감도 점수 자체를 언급하지는 마.)"
        history_for_api.append({'role': 'user', 'parts': [likability_context_prompt]})
        print(f"DEBUG: process_message_batch - API 전달용 기록 생성됨 (총 {len(history_for_api)} 턴)")

        async with channel.typing():
            new_likability = current_likability; save_needed = False
            bot_response_text_full = "" # 생성된 전체 응답 저장용
            final_text_to_send = "" # 최종 전송 텍스트

            try:
                print("DEBUG: process_message_batch - 1단계: 전체 응답 생성 시도...")
                # Generation Config (길이 제한 제거됨)
                generation_config = None # 또는 genai_types.GenerationConfig() 객체

                response = await model.generate_content_async(
                    history_for_api,
                    generation_config=generation_config
                )

                if not (response and response.text): raise Exception("Initial generation failed or blocked")

                bot_response_text_full = response.text.strip()
                print(f"DEBUG: process_message_batch - 1단계 생성 전체 응답: {bot_response_text_full[:100]}...")

                # 2단계: 길이 확인 및 필요시 요약 (3문장 초과 시)
                sentences = re.split(r'(?<=[.?!])\s+', bot_response_text_full)
                if len(sentences) > 3:
                    print(f"DEBUG: process_message_batch - 답변이 {len(sentences)} 문장으로 길어서 요약 시도...")
                    summarized_text = await summarize_text(model, bot_response_text_full)
                    if summarized_text: final_text_to_send = summarized_text
                    else: print("경고: 요약 실패. 원본 답변의 첫 3문장 사용."); final_text_to_send = " ".join(sentences[:3])
                else: print("DEBUG: process_message_batch - 답변이 3문장 이하이므로 원본 사용."); final_text_to_send = bot_response_text_full

                # 성공 시 호감도 계산
                new_likability = await calculate_likability(model, current_likability, combined_message_content)
                # 실제 기록에는 항상 전체 응답 저장
                current_history.append({'role': 'user', 'parts': [combined_message_content]})
                current_history.append({'role': 'model', 'parts': [bot_response_text_full]}) # 전체 응답 저장
                save_needed = True

                # 3단계: 최종 텍스트 분할 전송
                print(f"DEBUG: process_message_batch - 최종 전송할 텍스트: {final_text_to_send[:100]}...")
                final_sentences = re.split(r'(?<=[.?!])\s+', final_text_to_send)
                for sentence in final_sentences:
                    sentence = sentence.strip()
                    if sentence: await channel.send(sentence); await asyncio.sleep(random.uniform(1.0, 2.0))

            except Exception as e:
                print(f"오류: User {user_id} 메시지 처리(요약 포함) 중 - {e}")
                if not final_text_to_send: await channel.send("미안, 방금 하신 말씀들을 처리하는 데 문제가 생겼어요. 😥")
            finally:
                # DB 저장 (성공 시에만)
                if save_needed: print(f"DEBUG: process_message_batch - 저장 함수 호출 전 기록 (총 {len(current_history)} 턴), 새 호감도: {new_likability}"); save_user_data(user_id, current_history, new_likability)
                else: print(f"DEBUG: process_message_batch - DB 저장 건너뜀.")

    else: print(f"DEBUG: process_message_batch - 사용자 ID {user_id} 버퍼가 이미 비어있음.")
    if user_id in user_timer_tasks: del user_timer_tasks[user_id]; print(f"DEBUG: process_message_batch - 타이머 작업 최종 제거됨")


# --- 요약 함수 정의 ---
async def summarize_text(model, text_to_summarize, max_sentences=3):
    """ Gemini를 사용하여 주어진 텍스트를 요약합니다. """
    print(f"DEBUG: summarize_text 호출됨 - 요약 대상 (시작): '{text_to_summarize[:50]}...'")
    try:
        summary_prompt = prompts.SUMMARIZE_PROMPT_TEMPLATE.format(text_to_summarize=text_to_summarize)
        generation_config_summary = genai_types.GenerationConfig(max_output_tokens=200)
        summary_response = await model.generate_content_async(summary_prompt, generation_config=generation_config_summary)
        if summary_response and summary_response.text:
            summarized_text = summary_response.text.strip()
            print(f"DEBUG: 요약 성공 - 요약 결과: {summarized_text}")
            return summarized_text
        else: print(f"경고: 요약 API 응답 비었거나 문제 있음."); return None
    except Exception as e: print(f"오류: 요약 API 호출 중 오류 발생: {e}"); return None


# --- 봇 이벤트 핸들러 ---
@bot.event
async def on_ready():
    init_db()
    print(f'로그인 성공: {bot.user.name} ({bot.user.id})')
    print(f'애플리케이션 ID: {DISCORD_APP_ID}'); print('------')
    print('봇이 준비되었습니다! DM 메시지를 기다립니다...')
    if not send_proactive_dm.is_running():
        try: print("DEBUG: 선톡 작업 시작 시도..."); send_proactive_dm.start(); print('DEBUG: 선톡 보내기 백그라운드 작업 start() 호출 완료.')
        except Exception as e: print(f"오류: 선톡 작업 시작(start) 중 예외 발생: {e}")
    else: print("DEBUG: 선톡 작업은 이미 실행 중입니다.")


@bot.event
async def on_message(message):
    # --- !!! 전역 변수 사용 선언 확인 !!! ---
    global user_message_buffers, user_timer_tasks
    # ------------------------------------
    if message.author == bot.user: return
    if message.guild is not None: return # DM만 처리

    ctx = await bot.get_context(message)
    if ctx.command is not None:
        print(f"DEBUG: on_message - 명령어 감지됨: '{message.content}' -> 처리를 process_commands에 넘김")
        await bot.process_commands(message) # 명령어는 여기서 처리
        return

    # 일반 DM 메시지 버퍼링 및 타이머 처리
    user_id = message.author.id
    print(f"[DM 수신] {message.author.name}: {message.content}")
    if user_id not in user_message_buffers: user_message_buffers[user_id] = []
    user_message_buffers[user_id].append(message)
    print(f"DEBUG: 메시지 버퍼 추가됨 - 사용자 ID: {user_id}, 현재 버퍼 크기: {len(user_message_buffers[user_id])}")
    if user_id in user_timer_tasks:
        existing_task = user_timer_tasks[user_id]
        if not existing_task.done(): print(f"DEBUG: 기존 타이머 취소 시도 - 사용자 ID: {user_id}"); existing_task.cancel()

    async def delayed_process(uid):
        try:
            await asyncio.sleep(20)
            print(f"DEBUG: 20초 타이머 만료 - 사용자 ID: {uid}, 처리 함수 호출 시도.")
            await process_message_batch(uid)
        except asyncio.CancelledError: print(f"DEBUG: 타이머 작업 정상 취소됨 (새 메시지 수신) - 사용자 ID: {uid}")
        except Exception as e:
             print(f"오류: delayed_process 작업 중 예외 발생 - 사용자 ID: {uid}, 오류: {e}"); traceback.print_exc()
             # --- !!! 여기 들여쓰기 확인 !!! ---
             if uid in user_timer_tasks:
                 del user_timer_tasks[uid] # if 안에 있어야 함
                 print(f"DEBUG: 오류 발생 후 타이머 작업 정리됨 - 사용자 ID: {uid}")
             if uid in user_message_buffers:
                 del user_message_buffers[uid] # if 안에 있어야 함
                 print(f"DEBUG: 오류 발생 후 메시지 버퍼 정리됨 - 사용자 ID: {uid}")
             # ---------------------------

    print(f"DEBUG: 새 타이머 시작 (20초) - 사용자 ID: {user_id}")
    user_timer_tasks[user_id] = asyncio.create_task(delayed_process(user_id))


# --- 선톡 보내는 백그라운드 작업 (요약 로직 추가됨) ---
@tasks.loop(minutes=30)
async def send_proactive_dm():
    try:
        user = await bot.fetch_user(TARGET_USER_ID)
        if user:
            print(f"선톡 대상 확인: {user.name} ({TARGET_USER_ID})")
            target_user_history, target_user_likability = load_user_data(TARGET_USER_ID)
            print(f"DEBUG: 선톡 - 로드됨 -> 기록 (총 {len(target_user_history)} 턴), 호감도: {target_user_likability}")
            proactive_instruction = prompts.PROACTIVE_DM_PROMPT_TEMPLATE.format(user_display_name=user.display_name)
            history_with_instruction = target_user_history.copy()
            history_with_instruction.append({'role': 'user', 'parts': [proactive_instruction]})
            print(f"DEBUG: 선톡 - Gemini에게 전달할 프롬프트(마지막 지시): {proactive_instruction}")

            message_to_send_full = random.choice(prompts.PROACTIVE_DM_FALLBACKS)
            generated_text = ""

            try:
                print("DEBUG: 선톡 - 1단계: 전체 응답 생성 시도...")
                response = await model.generate_content_async(history_with_instruction)
                if response and response.text: generated_text = response.text.strip(); message_to_send_full = generated_text; print(f"Gemini 생성 메시지 (선톡, 전체): {message_to_send_full[:100]}...")
                else: print(f"경고: Gemini 응답 비었거나 차단됨. 기본 메시지 사용.")
            except Exception as e: print(f"오류: Gemini 메시지 생성 중 오류 발생 - {e}")

            # 2단계: 길이 확인 및 필요시 요약
            final_text_to_send = message_to_send_full
            sentences = re.split(r'(?<=[.?!])\s+', message_to_send_full)
            if len(sentences) > 3:
                print(f"DEBUG: 선톡 - 답변이 {len(sentences)} 문장으로 길어서 요약 시도...")
                summarized_text = await summarize_text(model, message_to_send_full)
                if summarized_text: final_text_to_send = summarized_text
                else: print("경고: 선톡 요약 실패. 원본 답변의 첫 3문장 사용."); final_text_to_send = " ".join(sentences[:3])
            else: print("DEBUG: 선톡 - 답변이 3문장 이하이므로 원본 사용.")

            # 3단계: 최종 텍스트 분할 전송 및 DB 저장
            print(f"선톡 시도 -> User ID: {TARGET_USER_ID}, 메시지 (최종): {final_text_to_send[:100]}...")
            if final_text_to_send:
                 final_sentences = re.split(r'(?<=[.?!])\s+', final_text_to_send)
                 for sentence in final_sentences:
                     sentence = sentence.strip()
                     if sentence: await user.send(sentence); await asyncio.sleep(random.uniform(1.0, 2.0))
                 print(f"선톡 성공 (분할 전송 완료) -> User ID: {TARGET_USER_ID}")
                 final_history_to_save = target_user_history
                 final_history_to_save.append({'role': 'model', 'parts': [message_to_send_full]}) # 원본 전체 저장
                 save_user_data(TARGET_USER_ID, final_history_to_save, target_user_likability)
                 print(f"선톡 내용(원본) DB 저장 완료 -> User ID: {TARGET_USER_ID}, 호감도: {target_user_likability}")
            else: print(f"경고: 최종적으로 보낼 메시지가 없습니다.")
    except discord.NotFound: print(f"오류: 선톡 대상 사용자를 찾을 수 없습니다 (ID: {TARGET_USER_ID})")
    except discord.Forbidden: print(f"오류: 선톡 대상 사용자에게 DM을 보낼 권한이 없습니다 (ID: {TARGET_USER_ID})")
    except Exception as e: print(f"선톡 작업 중 예외 발생: {e}")


@send_proactive_dm.before_loop
async def before_proactive_dm():
    print('DEBUG: 선톡 before_loop 진입.')
    await bot.wait_until_ready()
    print('DEBUG: 선톡 before_loop - 봇 준비 완료됨.')
    print('선톡 작업: 봇 준비 완료, 루프 시작.')

@send_proactive_dm.error
async def send_proactive_dm_error(error):
    print(f"오류: 선톡 작업 루프(@tasks.loop) 내에서 처리되지 않은 예외 발생!")
    traceback.print_exception(type(error), error, error.__traceback__)


# --- Cog 로딩을 위한 별도 async 함수 ---
async def load_cogs():
    print("Cog 로딩 시작 (load_cogs 함수)...")
    cog_loaded = False
    if not os.path.exists('./cogs'): print("경고: './cogs' 폴더를 찾을 수 없습니다."); return
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            extension_name = f'cogs.{filename[:-3]}'
            try: await bot.load_extension(extension_name); print(f" - Cog 로드 성공: {extension_name}"); cog_loaded = True
            except Exception as e: print(f" ! Cog 로드 실패: {extension_name}\n   오류: {e}"); traceback.print_exc()
    if not cog_loaded: print("경고: 로드된 Cog가 없습니다."); print("------")


# --- 스크립트 실행 진입점 ---
if __name__ == "__main__":
    try:
        print("DEBUG: Cog 로딩 시도 (asyncio.run(load_cogs()) 호출 전).")
        asyncio.run(load_cogs())
        print("DEBUG: Cog 로딩 완료됨.")
        print("------")
        print("DEBUG: bot.run(DISCORD_TOKEN) 호출 시도...")
        bot.run(DISCORD_TOKEN) # 봇 실행
    except KeyboardInterrupt: print("사용자에 의해 봇 실행 중단됨 (KeyboardInterrupt).")
    except discord.errors.LoginFailure: print("오류: 디스코드 봇 토큰이 잘못되었습니다. .env 파일을 확인하세요.")
    except Exception as e: print(f"스크립트 실행 중 최상위 레벨 예외 발생: {e}"); traceback.print_exc()
    finally: print("봇 프로그램 종료.")