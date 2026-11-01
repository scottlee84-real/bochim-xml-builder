import streamlit as st
import os
import re
import cv2
import pandas as pd
from mutagen import File as MutagenFile

# -------------------------------------------------------------
# 1. 페이지 기본 설정
# -------------------------------------------------------------
st.set_page_config(
    page_title="보김 프리미어 XML 마스터 빌더",
    page_icon="🎬",
    layout="wide"
)

st.title("🎬 보김 프리미어 프로 XML 마스터 빌더")
st.caption("구글 드라이브 미디어 파일의 실제 메타데이터(FPS, 재생 시간)를 분석하여 무결점 FCP XML을 조립합니다.")

# -------------------------------------------------------------
# 2. 미디어 메타데이터 분석 헬퍼 함수군
# -------------------------------------------------------------
def get_video_info(filepath):
    """OpenCV로 비디오의 실제 프레임 수, FPS, 해상도 측정"""
    try:
        cap = cv2.VideoCapture(filepath)
        if not cap.isOpened():
            return None
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080
        cap.release()
        duration = total_frames / fps if fps > 0 else 0.0
        return {
            "fps": fps,
            "total_frames": total_frames,
            "width": width,
            "height": height,
            "duration": duration
        }
    except Exception:
        return None

def get_audio_info(filepath):
    """Mutagen으로 나레이션 오디오 실제 길이 및 샘플레이트 측정"""
    try:
        audio = MutagenFile(filepath)
        if audio and audio.info:
            return {
                "duration": audio.info.length,
                "samplerate": getattr(audio.info, "sample_rate", 44100)
            }
    except Exception:
        pass
    return {"duration": 0.0, "samplerate": 44100}

def parse_filename_numbers(filename):
    """01.jpg -> scene: 1, sub: 1 | 09-1.mp4 -> scene: 9, sub: 1 | 11.mp4 -> scene: 11, sub: 1"""
    base = os.path.splitext(filename)[0]
    sub_match = re.search(r'(?:^|[^\d])(\d+)[-_](\d+)(?:[^\d]|$)', base)
    if sub_match:
        return int(sub_match.group(1)), int(sub_match.group(2))
    single_match = re.search(r'(?:^|[^\d])(\d+)(?:[^\d]|$)', base)
    if single_match:
        return int(single_match.group(1)), 1
    return None, None

def parse_time_str(t_str):
    """MM:SS 또는 HH:MM:SS 문자열을 초 단위로 변환"""
    parts = list(map(float, t_str.strip().split(":")))
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return 0.0

# -------------------------------------------------------------
# 3. 사이드바 - 프로젝트 작업 경로 설정 (보안 유지)
# -------------------------------------------------------------
with st.sidebar:
    st.header("📁 작업 환경 설정")
    base_dir = st.text_input(
        "Bochim_Production 루트 경로",
        value=st.secrets.get("DEFAULT_BASE_DIR", r"G:\내 드라이브\Bochim_Production"),
        help="Google Drive 데스크톱이 동기화된 Bochim_Production 로컬 폴더 경로"
    )
    
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
    else:
        st.info("💡 경로를 확인하거나 아래에 프로젝트명을 직접 적어주세요.")
        project_name = st.text_input("프로젝트 폴더명 직접 입력", value="2026-10-04_유월절_01")
        project_dir = os.path.join(base_dir, project_name)

    target_fps = st.selectbox("시퀀스 기준 타임베이스(FPS)", options=[30, 24, 25, 60], index=0)

# -------------------------------------------------------------
# 4. 프로젝트 폴더 스캔 및 데이터 로드
# -------------------------------------------------------------
st.markdown("---")
st.subheader(f"📌 대상 프로젝트: `{project_name}`")

if not os.path.exists(project_dir):
    st.warning(f"⚠️ 폴더를 찾을 수 없습니다: `{project_dir}`")
    st.stop()

audio_dir = os.path.join(project_dir, "01_Audio")
media_candidates = ["02_Media", "02_Images", "03_Videos"]
existing_media_dirs = [os.path.join(project_dir, d) for d in media_candidates if os.path.exists(os.path.join(project_dir, d))]

# 1) 오디오 파일 스캔
audio_file = None
audio_meta = {"duration": 0.0, "samplerate": 44100}
if os.path.exists(audio_dir):
    for f in os.listdir(audio_dir):
        if f.lower().endswith((".mp3", ".wav", ".m4a", ".aac")):
            audio_file = f
            audio_path = os.path.join(audio_dir, f)
            audio_meta = get_audio_info(audio_path)
            break

# 2) 대본 타임코드 스캔 (SRT 자막 또는 CSV)
scenes_timeline = []

if os.path.exists(audio_dir):
    srt_files = [f for f in os.listdir(audio_dir) if f.lower().endswith(".srt")]
    if srt_files:
        srt_path = os.path.join(audio_dir, srt_files[0])
        try:
            with open(srt_path, "r", encoding="utf-8") as sf:
                srt_text = sf.read()
            blocks = srt_text.strip().replace("\r\n", "\n").split("\n\n")
            idx = 1
            for block in blocks:
                lines = block.split("\n")
                if len(lines) >= 3 and "-->" in lines[1]:
                    t_parts = lines[1].split("-->")
                    def srt_to_sec(s):
                        h, m, sec_ms = s.strip().split(":")
                        sec, ms = sec_ms.replace(",", ".").split(".")
                        return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000.0
                    st_sec = srt_to_sec(t_parts[0])
                    ed_sec = srt_to_sec(t_parts[1])
                    sub_text = " ".join(lines[2:])
                    scenes_timeline.append({
                        "scene": idx,
                        "start_sec": st_sec,
                        "end_sec": ed_sec,
                        "script": sub_text
                    })
                    idx += 1
        except Exception as e:
            st.warning(f"SRT 읽기 알림: {e}")

if not scenes_timeline:
    csv_candidates = [f for f in os.listdir(project_dir) if f.lower().endswith(".csv")]
    if csv_candidates:
        csv_path = os.path.join(project_dir, csv_candidates[0])
        try:
            df_csv = pd.read_csv(csv_path)
            for _, row in df_csv.iterrows():
                s_num_str = str(row.get("씬 번호", row.iloc[0]))
                tc_str = str(row.get("타임코드", row.iloc[1]))
                script_str = str(row.get("확정 대사", row.get("대사", row.iloc[2])))
                
                s_match = re.search(r'\d+', s_num_str)
                s_num = int(s_match.group()) if s_match else len(scenes_timeline) + 1
                
                start_sec, end_sec = 0.0, 5.0
                if "-" in tc_str:
                    parts = tc_str.split("-")
                    start_sec = parse_time_str(parts[0])
                    end_sec = parse_time_str(parts[1])
                scenes_timeline.append({
                    "scene": s_num,
                    "start_sec": start_sec,
                    "end_sec": end_sec,
                    "script": script_str
                })
        except Exception as e:
            st.warning(f"CSV 읽기 알림: {e}")

# 3) 미디어 파일 스캔 및 분석
img_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}
vid_exts = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
media_assets = {}

for m_dir in existing_media_dirs:
    for f in os.listdir(m_dir):
        ext = os.path.splitext(f)[1].lower()
        if ext in img_exts or ext in vid_exts:
            s_num, s_sub = parse_filename_numbers(f)
            if s_num is not None:
                full_path = os.path.join(m_dir, f)
                rel_path = os.path.relpath(full_path, project_dir).replace("\\", "/")
                is_vid = ext in vid_exts
                meta = get_video_info(full_path) if is_vid else None
                
                if s_num not in media_assets:
                    media_assets[s_num] = []
                media_assets[s_num].append({
                    "type": "video" if is_vid else "image",
                    "sub": s_sub,
                    "filename": f,
                    "abspath": full_path,
                    "relpath": rel_path,
                    "meta": meta
                })

# -------------------------------------------------------------
# 5. 분석 현황 대시보드
# -------------------------------------------------------------
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("총 타임라인 씬", f"{len(scenes_timeline)} 개")
with col2:
    aud_status = f"✅ {audio_file} ({audio_meta['duration']:.1f}초)" if audio_file else "❌ 오디오 없음"
    st.metric("나레이션 오디오", aud_status)
with col3:
    total_files = sum(len(v) for v in media_assets.values())
    st.metric("발견된 미디어 에셋", f"{total_files} 개")

table_rows = []
for sc in scenes_timeline:
    s_idx = sc["scene"]
    assets = media_assets.get(s_idx, [])
    dur_expected = sc["end_sec"] - sc["start_sec"]
    
    if assets:
        status_label = f"🟢 준비됨 ({len(assets)}개)"
        detail_list = []
        for a in assets:
            if a["type"] == "video":
                v_dur = a["meta"]["duration"] if a["meta"] else 0.0
                v_fps = a["meta"]["fps"] if a["meta"] else 0.0
                detail_list.append(f"🎥 {a['filename']} ({v_dur:.1f}s / {v_fps:.0f}fps)")
            else:
                detail_list.append(f"🖼️ {a['filename']} (스틸)")
        details = ", ".join(detail_list)
    else:
        status_label = "⚪ 빈 슬롯 (Gap)"
        details = "에셋 없음 (빈 공간 유지)"

    table_rows.append({
        "씬": f"Scene #{s_idx}",
        "시간 구간": f"{sc['start_sec']:.1f}s ~ {sc['end_sec']:.1f}s ({dur_expected:.1f}s)",
        "대사 미리보기": sc["script"][:30] + "..." if len(sc["script"]) > 30 else sc["script"],
        "상태": status_label,
        "매핑된 에셋 메타데이터": details
    })

if table_rows:
    st.dataframe(pd.DataFrame(table_rows), use_container_width=True)
else:
    st.info("💡 `01_Audio` 폴더에 `.srt` 자막 파일이 있거나 프로젝트 루트에 `.csv` 파일이 있으면 씬 타임라인이 자동으로 인식됩니다.")

# -------------------------------------------------------------
# 6. FCP XML 완성 엔진 함수
# -------------------------------------------------------------
def build_fcp_xml(proj_name, scenes, assets_map, audio_name, aud_meta, target_fps=30):
    fps = target_fps
    total_frames = 0
    video_clips_xml = ""
    clip_counter = 1

    for sc in scenes:
        s_num = sc["scene"]
        scene_start_frame = int(round(sc["start_sec"] * fps))
        scene_end_frame = int(round(sc["end_sec"] * fps))
        scene_duration_frames = max(scene_end_frame - scene_start_frame, fps * 2)
        total_frames = max(total_frames, scene_end_frame)

        raw_list = assets_map.get(s_num, [])
        if not raw_list:
            continue

        # 동일 서브 번호에 비디오가 있으면 비디오 우선 배치
        sub_groups = {}
        for item in raw_list:
            sub = item["sub"]
            if sub not in sub_groups:
                sub_groups[sub] = item
            elif sub_groups[sub]["type"] == "image" and item["type"] == "video":
                sub_groups[sub] = item

        sorted_subs = sorted(sub_groups.keys())
        active_assets = [sub_groups[s] for s in sorted_subs]
        count = len(active_assets)

        frames_per_clip = scene_duration_frames // count
        curr_start = scene_start_frame

        for k, asset in enumerate(active_assets):
            is_last = (k == count - 1)
            clip_dur = (scene_end_frame - curr_start) if is_last else frames_per_clip
            clip_end = curr_start + clip_dur
            
            # 비디오 유효 프레임 측정 및 클리핑
            if asset["type"] == "video" and asset["meta"]:
                fps_ratio = fps / asset["meta"]["fps"] if asset["meta"]["fps"] > 0 else 1.0
                native_frames = int(asset["meta"]["total_frames"] * fps_ratio)
                in_point = 0
                out_point = min(clip_dur, native_frames) if native_frames > 0 else clip_dur
                file_dur = native_frames if native_frames > 0 else clip_dur
            else:
                in_point = 0
                out_point = clip_dur
                file_dur = 108000

            # 프리미어 프로 표준 로컬 URL 형식 (G:/내 드라이브/...)
            abs_formatted = asset["abspath"].replace("\\", "/")
            abs_url = f"file://localhost/{abs_formatted}"

            video_clips_xml += f"""
          <clipitem id="clipitem-v-{clip_counter}">
            <name>Scene #{s_num} - {asset['filename']}</name>
            <duration>{clip_dur}</duration>
            <rate>
              <timebase>{fps}</timebase>
              <ntsc>FALSE</ntsc>
            </rate>
            <start>{curr_start}</start>
            <end>{clip_end}</end>
            <in>{in_point}</in>
            <out>{out_point}</out>
            <file id="file-v-{clip_counter}">
              <name>{asset['filename']}</name>
              <pathurl>{abs_url}</pathurl>
              <rate>
                <timebase>{fps}</timebase>
                <ntsc>FALSE</ntsc>
              </rate>
              <duration>{file_dur}</duration>
              <media>
                <video>
                  <samplecharacteristics>
                    <width>1920</width>
                    <height>1080</height>
                  </samplecharacteristics>
                </video>
              </media>
            </file>
          </clipitem>"""
            curr_start = clip_end
            clip_counter += 1

    # 오디오 실제 길이에 맞추어 전체 시퀀스 런타임 프레임 최종 확장
    if aud_meta["duration"] > 0:
        aud_total_frames = int(round(aud_meta["duration"] * fps))
        total_frames = max(total_frames, aud_total_frames)

    # A1 나레이션 오디오 트랙 조립
    audio_track_xml = ""
    if audio_name:
        aud_abs_formatted = os.path.join(audio_dir, audio_name).replace("\\", "/")
        abs_aud_url = f"file://localhost/{aud_abs_formatted}"
        audio_track_xml = f"""
      <audio>
        <track>
          <clipitem id="clipitem-a-1">
            <name>{audio_name}</name>
            <duration>{total_frames}</duration>
            <rate>
              <timebase>{fps}</timebase>
              <ntsc>FALSE</ntsc>
            </rate>
            <start>0</start>
            <end>{total_frames}</end>
            <in>0</in>
            <out>{total_frames}</out>
            <file id="file-audio-1">
              <name>{audio_name}</name>
              <pathurl>{abs_aud_url}</pathurl>
              <rate>
                <timebase>{fps}</timebase>
                <ntsc>FALSE</ntsc>
              </rate>
              <duration>{total_frames}</duration>
              <media>
                <audio>
                  <samplecharacteristics>
                    <depth>16</depth>
                    <samplerate>{aud_meta['samplerate']}</samplerate>
                  </samplecharacteristics>
                  <channelcount>2</channelcount>
                </audio>
              </media>
            </file>
          </clipitem>
        </track>
      </audio>"""

    # 최종 xmeml v4 XML 조립
    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xmeml>
<xmeml version="4">
  <sequence>
    <name>{proj_name}_AutoTimeline</name>
    <duration>{total_frames}</duration>
    <rate>
      <timebase>{fps}</timebase>
      <ntsc>FALSE</ntsc>
    </rate>
    <timecode>
      <rate>
        <timebase>{fps}</timebase>
        <ntsc>FALSE</ntsc>
      </rate>
      <string>00:00:00:00</string>
      <frame>0</frame>
      <displayformat>NDF</displayformat>
    </timecode>
    <media>
      <video>
        <format>
          <samplecharacteristics>
            <width>1920</width>
            <height>1080</height>
            <pixelaspectratio>square</pixelaspectratio>
          </samplecharacteristics>
        </format>
        <track>
{video_clips_xml}
        </track>
      </video>
{audio_track_xml}
    </media>
  </sequence>
</xmeml>"""
    return xml_content

# -------------------------------------------------------------
# 7. 실행 및 다운로드 인터페이스
# -------------------------------------------------------------
st.markdown("---")
btn_col1, btn_col2 = st.columns([3, 7])

with btn_col1:
    if st.button("🚀 프리미어 프로 XML 빌드 & 자동 저장", type="primary", use_container_width=True):
        if not scenes_timeline:
            st.error("타임라인 씬 데이터가 없습니다.")
        else:
            final_xml = build_fcp_xml(project_name, scenes_timeline, media_assets, audio_file, audio_meta, target_fps)
            
            # 프로젝트 폴더 내 자동 저장
            out_xml_path = os.path.join(project_dir, f"{project_name}_AutoTimeline.xml")
            try:
                with open(out_xml_path, "w", encoding="utf-8") as xf:
                    xf.write(final_xml)
                st.success(f"✅ 구글 드라이브 폴더에 즉시 저장 완료!\n파일명: `{project_name}_AutoTimeline.xml`")
            except Exception as e:
                st.warning(f"로컬 파일 쓰기 권한 알림: {e}")

            # 브라우저 수동 다운로드 지원
            st.download_button(
                label="📥 XML 수동 다운로드 (.xml)",
                data=final_xml.encode("utf-8"),
                file_name=f"{project_name}_AutoTimeline.xml",
                mime="application/xml",
                use_container_width=True
            )
