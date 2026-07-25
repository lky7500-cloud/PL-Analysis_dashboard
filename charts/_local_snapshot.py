"""
charts/07~09 공용 로컬 스냅샷 로더.

BigQuery 인증/연결에 실패했을 때, 각 스크립트가 ../data/ 폴더의 로컬 엑셀
스냅샷(app.py가 쓰는 것과 동일한 원본 파일)으로 자동 전환하기 위한 헬퍼.
"""

import os

import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def load_local_tables():
    """(sales, product, gl_classified, budget) 튜플을 반환한다."""
    sales = pd.read_excel(os.path.join(DATA_DIR, "05_매출상세.xlsx"))
    product = pd.read_excel(os.path.join(DATA_DIR, "02_제품마스터.xlsx"))
    account = pd.read_excel(os.path.join(DATA_DIR, "03_계정과목마스터.xlsx"))
    gl = pd.read_excel(os.path.join(DATA_DIR, "06_GL원장.xlsx"))
    budget = pd.read_excel(os.path.join(DATA_DIR, "04_예산.xlsx"))

    gl_classified = gl.merge(account[["계정코드", "계정분류"]], on="계정코드", how="left")
    return sales, product, gl_classified, budget
