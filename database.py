# -*- coding: utf-8 -*-
# database.py (config.py 사용하도록 수정)

import psycopg2
import json
import os
import config # <-- config.py 임포트 추가

# --- !!! DEFAULT_LIKABILITY 정의 삭제 !!! ---
# 삭제 --> DEFAULT_LIKABILITY = 50
# ---------------------------------------

# .env 에서 DB 접속 정보 읽기
DATABASE_URL = os.getenv('DATABASE_URL')

def get_db_connection():
    """데이터베이스 커넥션을 생성하고 반환합니다."""
    # print(f"DEBUG: get_db_connection 함수 호출됨.") # 필요 시 주석 해제
    db_url = os.getenv('DATABASE_URL') # 함수 내부에서 읽기
    if not db_url:
         print("오류: DATABASE_URL 환경 변수를 찾을 수 없습니다! (.env 파일 또는 Replit Secrets 확인)")
         return None
    try:
        # print(f"DEBUG: psycopg2.connect 시도: URL='{db_url}'")
        conn = psycopg2.connect(db_url)
        # print("DEBUG: psycopg2.connect 성공!")
        return conn
    except psycopg2.Error as e:
        print(f"데이터베이스 연결 오류: {e}")
        # print(f"DEBUG: 연결 실패 시 사용된 DATABASE_URL: '{db_url}'")
        return None

def init_db():
    """데이터베이스와 테이블 초기화 (없으면 생성, 있으면 likability 컬럼 추가 시도)"""
    conn = get_db_connection()
    if conn is None: return
    try:
        with conn:
            with conn.cursor() as cursor:
                # 기본값을 config 에서 가져옴
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS conversations (
                        user_id BIGINT PRIMARY KEY,
                        history TEXT,
                        likability INTEGER DEFAULT %s
                    )
                ''', (config.DEFAULT_LIKABILITY_SCORE,)) # <-- config 사용
                print("테이블 'conversations' 확인/생성 완료.")
                try:
                    # 기본값을 config 에서 가져옴
                    cursor.execute('ALTER TABLE conversations ADD COLUMN IF NOT EXISTS likability INTEGER DEFAULT %s', (config.DEFAULT_LIKABILITY_SCORE,)) # <-- config 사용
                    print("'likability' 컬럼 확인/추가 완료.")
                except psycopg2.Error as alter_err:
                     print(f"경고: 'likability' 컬럼 추가/확인 중 오류: {alter_err}")
        print(f"데이터베이스 초기화 작업 완료.")
    except psycopg2.Error as e: print(f"데이터베이스 초기화 중 오류 발생: {e}")
    finally:
        if conn: conn.close()

def load_user_data(user_id):
    """DB에서 특정 사용자의 대화 기록과 호감도 로드"""
    conn = get_db_connection()
    # 기본값을 config 에서 가져옴
    if conn is None: return [], config.DEFAULT_LIKABILITY_SCORE # <-- config 사용
    # print(f"DEBUG: 데이터 로딩 시도 - 사용자 ID: {user_id}") # 필요 시 주석 해제
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT history, likability FROM conversations WHERE user_id = %s", (user_id,))
                result = cursor.fetchone()
                if result:
                    history_json = result[0] if result[0] else '[]'
                    # 기본값을 config 에서 가져옴
                    likability = result[1] if result[1] is not None else config.DEFAULT_LIKABILITY_SCORE # <-- config 사용
                    # print(f"DEBUG: 로딩 성공 - DB 내용 (JSON 시작 부분): {history_json[:100]}...")
                    try: history_list = json.loads(history_json)
                    except json.JSONDecodeError: print(f"경고: 사용자 {user_id}의 history JSON 파싱 오류. 빈 리스트 반환."); history_list = []
                    # print(f"DEBUG: 로딩 성공 - 변환된 리스트 (총 {len(history_list)} 턴), 호감도: {likability}")
                    return history_list, likability
                else: print(f"DEBUG: 로딩 - 사용자 ID {user_id}에 대한 기록 없음. 기본값 반환."); return [], config.DEFAULT_LIKABILITY_SCORE # <-- config 사용
    except psycopg2.Error as e: print(f"사용자 {user_id} 데이터 로드 중 오류 발생: {e}"); return [], config.DEFAULT_LIKABILITY_SCORE # <-- config 사용
    finally:
        if conn: conn.close()

def save_user_data(user_id, history_list, likability_score):
    """특정 사용자의 대화 기록과 호감도를 DB에 저장 (덮어쓰기)"""
    conn = get_db_connection()
    if conn is None: return
    # print(f"DEBUG: 저장 시도 - 사용자 ID: {user_id}, 저장할 기록 턴 수: {len(history_list)}, 호감도: {likability_score}") # 필요 시 주석 해제
    try:
        with conn:
            with conn.cursor() as cursor:
                history_json = json.dumps(history_list, ensure_ascii=False)
                # print(f"DEBUG: 저장할 JSON (시작 부분): {history_json[:100]}...")
                cursor.execute("""
                    INSERT INTO conversations (user_id, history, likability)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        history = EXCLUDED.history,
                        likability = EXCLUDED.likability;
                """, (user_id, history_json, likability_score))
                # print(f"DEBUG: 저장 쿼리 실행 완료 - 사용자 ID: {user_id}, 호감도: {likability_score}")
        # print(f"DEBUG: 저장 및 커밋 완료 - 사용자 ID: {user_id}")
    except psycopg2.Error as e: print(f"사용자 {user_id} 데이터 저장 중 오류 발생: {e}")
    except TypeError as e: print(f"사용자 {user_id} 기록 JSON 변환 중 오류 발생 (TypeError): {e}"); print(f"DEBUG: 저장 실패 데이터 (마지막 3개 턴): {history_list[-3:]}")
    finally:
        if conn: conn.close()

def get_all_user_ids():
    """DB에 저장된 모든 사용자의 ID 목록을 반환합니다."""
    conn = get_db_connection()
    if conn is None: return []
    user_ids = []
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT user_id FROM conversations")
                results = cursor.fetchall()
                user_ids = [row[0] for row in results]
                # print(f"DEBUG: get_all_user_ids - {len(user_ids)} 명의 사용자 ID 로드됨.") # 필요 시 주석 해제
    except psycopg2.Error as e:
        print(f"모든 사용자 ID 로드 중 오류 발생: {e}")
    finally:
        if conn: conn.close()
    return user_ids