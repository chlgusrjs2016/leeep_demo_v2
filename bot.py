# -*- coding: utf-8 -*-
# bot.py

import discord
from discord.ext import commands, tasks
import os
from dotenv import load_dotenv
import google.generativeai as genai
import asyncio
import traceback

# 분리된 모듈 임포트
from database import init_db
import prompts
import config
from message_handler import handle_new_message
from utils import send_proactive_message

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
    
    model = genai.GenerativeModel(
        SELECTED_MODEL,
        system_instruction=prompts.SYSTEM_INSTRUCTION
    )
    print(f"Gemini API 설정 및 모델({model.model_name}) 초기화 완료.")
except Exception as e: 
    print(f"Gemini API 설정 또는 모델 초기화 중 오류 발생: {e}")
    exit()

# --- Discord 봇 설정 ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)
bot.model = model  # 모델 인스턴스를 봇 객체에 저장

# --- 봇 이벤트 핸들러 ---
@bot.event
async def on_ready():
    init_db()
    print(f'로그인 성공: {bot.user.name} ({bot.user.id})')
    print(f'애플리케이션 ID: {DISCORD_APP_ID}')
    print('------')
    print('봇이 준비되었습니다! DM 메시지를 기다립니다...')
    
    if not send_proactive_dm.is_running():
        try:
            print("DEBUG: 선톡 작업 시작 시도...")
            send_proactive_dm.start()
            print('DEBUG: 선톡 보내기 백그라운드 작업 start() 호출 완료.')
        except Exception as e:
            print(f"오류: 선톡 작업 시작(start) 중 예외 발생: {e}")
    else:
        print("DEBUG: 선톡 작업은 이미 실행 중입니다.")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if message.guild is not None:
        return  # DM만 처리

    ctx = await bot.get_context(message)
    if ctx.command is not None:
        print(f"DEBUG: on_message - 명령어 감지됨: '{message.content}' -> 처리를 process_commands에 넘김")
        await bot.process_commands(message)  # 명령어는 여기서 처리
        return

    # 일반 DM 메시지 처리 로직 (분리된 모듈 사용)
    await handle_new_message(message, bot)

# --- 선톡 보내는 백그라운드 작업 ---
@tasks.loop(minutes=config.PROACTIVE_DM_INTERVAL_MINUTES)
async def send_proactive_dm():
    try:
        await send_proactive_message(bot)
    except Exception as e:
        print(f"선톡 작업 중 예외 발생: {e}")
        traceback.print_exc()

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
    
    if not os.path.exists('./cogs'):
        print("경고: './cogs' 폴더를 찾을 수 없습니다.")
        return
        
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            extension_name = f'cogs.{filename[:-3]}'
            try:
                await bot.load_extension(extension_name)
                print(f" - Cog 로드 성공: {extension_name}")
                cog_loaded = True
            except Exception as e:
                print(f" ! Cog 로드 실패: {extension_name}\n   오류: {e}")
                traceback.print_exc()
                
    if not cog_loaded:
        print("경고: 로드된 Cog가 없습니다.")
    print("------")

# --- 스크립트 실행 진입점 ---
if __name__ == "__main__":
    try:
        print("DEBUG: Cog 로딩 시도 (asyncio.run(load_cogs()) 호출 전).")
        asyncio.run(load_cogs())
        print("DEBUG: Cog 로딩 완료됨.")
        print("------")
        print("DEBUG: bot.run(DISCORD_TOKEN) 호출 시도...")
        bot.run(DISCORD_TOKEN)  # 봇 실행
    except KeyboardInterrupt:
        print("사용자에 의해 봇 실행 중단됨 (KeyboardInterrupt).")
    except discord.errors.LoginFailure:
        print("오류: 디스코드 봇 토큰이 잘못되었습니다. .env 파일을 확인하세요.")
    except Exception as e:
        print(f"스크립트 실행 중 최상위 레벨 예외 발생: {e}")
        traceback.print_exc()
    finally:
        print("봇 프로그램 종료.")