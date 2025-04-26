# -*- coding: utf-8 -*-
# cogs/commands_cog.py

import discord
from discord.ext import commands
# --- !!! database 에서 load_user_data 를 가져오도록 수정 !!! ---
from database import load_user_data, save_user_data # <-- save_user_data 추가

class CommandsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        print("Commands Cog 초기화 완료.")

    @commands.command(name='안녕')
    async def hello(self, ctx):
        # ... (기존 코드 동일) ...
        if ctx.guild is not None: await ctx.send("이 명령어는 DM에서만 사용할 수 있어요."); return
        user_name = ctx.author.mention
        await ctx.send(f'안녕하세요, {user_name}님! 만나서 반가워요!')


    @commands.command(name='기록')
    async def show_history(self, ctx, num_turns: int = 5):
        # ... (DM 체크 동일) ...
        if ctx.guild is not None: await ctx.send("이 명령어는 DM에서만 사용할 수 있어요."); return

        user_id = ctx.author.id
        print(f"DEBUG: !기록 명령어 실행 - 사용자 ID: {user_id}, 요청 턴 수: {num_turns}")

        # --- !!! DB 로드 함수 호출 수정 !!! ---
        # 이전: history = load_user_history(user_id)
        # 수정: load_user_data는 (history, likability) 튜플을 반환하므로 아래와 같이 받음
        history, _ = load_user_data(user_id) # 호감도 값은 _ 로 받아서 무시
        # ---------------------------------

        if not history: await ctx.send("아직 저장된 대화 기록이 없어요. 저랑 먼저 대화를 나눠보세요!"); return

        # --- 이하 포맷팅 및 전송 로직은 동일 ---
        formatted_history = f"--- 최근 {num_turns} 턴 대화 기록 ---\n"
        # ... (나머지 로직 동일) ...
        try: await ctx.send(f"```{formatted_history}```")
        except Exception as e: print(f"오류: !기록 메시지 전송 중 오류 발생 - {e}"); await ctx.send("기록을 보여주는데 문제가 발생했어요. 😥")

        # --- !!! 새로운 !호감도 명령어 함수 추가 !!! ---
    @commands.command(name='호감도')
    async def show_likability(self, ctx):
        """현재 봇과의 호감도 점수를 보여줍니다."""
        # DM 에서만 작동하도록 제한
        if ctx.guild is not None:
            await ctx.send("이 명령어는 DM에서만 사용할 수 있어요.")
            return

        user_id = ctx.author.id
        print(f"DEBUG: !호감도 명령어 실행 - 사용자 ID: {user_id}")

        try:
            # DB에서 데이터 로드 (기록은 무시하고 호감도만 사용)
            _, likability_score = load_user_data(user_id) # history는 _ 로 받아서 무시

            # 응답 메시지 생성 및 전송
            await ctx.send(f"현재 하늘이와의 호감도는 **{likability_score}점**이에요! 😊")

        except Exception as e:
            # DB 로드나 메시지 전송 중 오류 발생 시
            print(f"오류: !호감도 처리 중 오류 발생 - {e}")
            await ctx.send("호감도를 불러오는 중에 문제가 발생했어요. 😥")
    # --- !!! 명령어 함수 추가 끝 !!! ---

    # --- !!! 새로운 !호감도변경 명령어 함수 추가 !!! ---
    @commands.command(name='호감도변경')
    async def set_likability(self, ctx, new_score_str: str):
        """호감도 점수를 지정된 숫자로 수동 변경합니다. (테스트/관리용)"""
        # DM 에서만 작동하도록 제한
        if ctx.guild is not None:
            await ctx.send("이 명령어는 DM에서만 사용할 수 있어요.")
            return

        # 입력값이 숫자인지 확인하고 정수로 변환
        try:
            new_score = int(new_score_str)
            # (선택사항) 점수 범위 제한 (예: 0~100)
            # if not 0 <= new_score <= 100:
            #     await ctx.send("호감도 점수는 0에서 100 사이의 숫자여야 해요.")
            #     return

        except ValueError:
            # 숫자로 변환 실패 시 안내 메시지
            await ctx.send("명령어 뒤에 변경할 호감도 '숫자'를 정확히 입력해주세요. (예: `!호감도변경 75`)")
            return

        user_id = ctx.author.id
        print(f"DEBUG: !호감도변경 명령어 실행 - 사용자 ID: {user_id}, 목표 점수: {new_score}")

        try:
            # 현재 대화 기록을 불러옴 (호감도만 변경하고 기록은 유지하기 위해)
            current_history, _ = load_user_data(user_id)

            # DB에 새 호감도 점수와 기존 대화 기록 저장
            save_user_data(user_id, current_history, new_score) # history는 그대로, likability만 변경

            await ctx.send(f"알겠습니다! 호감도가 **{new_score}점**으로 변경되었습니다. 😊")

        except Exception as e:
            # DB 저장/로드 중 오류 발생 시
            print(f"오류: !호감도변경 처리 중 DB 오류 발생 - {e}")
            await ctx.send("호감도를 변경하는 중에 문제가 발생했어요. 😥")
    # --- !!! 명령어 함수 추가 끝 !!! ---

# Cog 로드를 위한 필수 setup 함수 (동일)
async def setup(bot):
    await bot.add_cog(CommandsCog(bot))
    print("Commands Cog 로드 완료.")