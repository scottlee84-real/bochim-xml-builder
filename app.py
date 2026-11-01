import streamlit as st
import os
import pandas as pd

# -------------------------------------------------------------
# 1. 페이지 기본 설정 (와이드 모드)
# -------------------------------------------------------------
st.set_page_config(
    page_title="보김 프리미어 XML 빌더",
    page_icon="🎬",
    layout="wide"
)

st.title("🎬 보김 프리미어 프로 XML 마스터 빌더")
st.caption("구글 시트 스토리보드와 드라이브 에셋(01_Audio, 02_Media)을 분석하여 완벽한 FCP XML을 조립합니다.")

# -------------------------------------------------------------
# 2. 사이드바 - 프로젝트 작업 경로 설정 (보안 처리)
# -------------------------------------------------------------
with st.sidebar:
    st.header("📁 작업 환경 설정")
    
    # 기본 경로는 로컬 사용자 입력으로 받되, 코드에는 개인정보 하드코딩 배제
    base_dir = st.text_input(
        "Bochim_Production 루트 경로",
        value=st.secrets.get("DEFAULT_BASE_DIR", r"G:\내 드라이브\Bochim_Production"),
        help="Google Drive 데스크톱이 동기화된 Bochim_Production 로컬 폴더 경로를 입력하세요."
    )
    
    # 폴더가 실제 존재하는지 확인
    available_projects = []
    if os.path.exists(base_dir):
        try:
            available_projects = [
                d for d in os.listdir(base_dir) 
                if os.path.isdir(os.path.join(base_dir, d))
            ]
        except Exception:
            available_projects = []

    if available_projects:
        project_name = st.selectbox("작업할 프로젝트 선택", options=available_projects)
        project_dir = os.path.join(base_dir, project_name)
        st.success(f"연결됨: {project_name}")
    else:
        st.info("💡 경로를 확인하거나 아래에 프로젝트명을 직접 적어주세요.")
        project_name = st.text_input("프로젝트 폴더명 직접 입력", value="2026-10-04_유월절_01")
        project_dir = os.path.join(base_dir, project_name)

    target_fps = st.selectbox("시퀀스 기준 FPS", options=[30, 24, 25, 60], index=0)

# -------------------------------------------------------------
# 3. 메인 작업 화면 상태 점검
# -------------------------------------------------------------
st.markdown("---")
st.subheader(f"📌 선택된 프로젝트: `{project_name}`")

if not os.path.exists(project_dir):
    st.warning(f"⚠️ 현재 경로에 해당 폴더가 존재하지 않습니다: `{project_dir}`\n\nPC에 구글 드라이브 데스크톱 앱이 켜져 있는지 확인해 주세요.")
else:
    # 하위 규격 폴더 탐색
    audio_path = os.path.join(project_dir, "01_Audio")
    media_path = os.path.join(project_dir, "02_Media")

    col1, col2 = st.columns(2)
    with col1:
        if os.path.exists(audio_path):
            audio_files = os.listdir(audio_path)
            st.success(f"🎙️ `01_Audio` 폴더 확인됨 (파일 {len(audio_files)}개)")
        else:
            st.error("❌ `01_Audio` 폴더가 없습니다.")

    with col2:
        if os.path.exists(media_path):
            media_files = os.listdir(media_path)
            st.success(f"🖼️/🎥 `02_Media` 폴더 확인됨 (파일 {len(media_files)}개)")
        else:
            st.error("❌ `02_Media` 폴더가 없습니다.")

st.info("다음 단계에서 실제 미디어 파일(FPS, 재생시간)을 분석하는 정밀 엔진 함수를 장착합니다.")
