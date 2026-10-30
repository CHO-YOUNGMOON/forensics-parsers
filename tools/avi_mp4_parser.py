"""
avi_mp4_parser.py
- 파일 시그니처(헤더 12바이트)로 포맷 판별함
- AVI, MP4 구조 파싱해서 결과 찍음.
"""
# [청크/박스 이동 공식 요약]
# AVI는 2바이트 정렬이라 패딩 계산까지 같이 해줘야 됨.
# AVI 공식: next_chunk = chunk_start + 8 + chunk_size + (chunk_size % 2)
# MP4는 보통 박스 끝으로 바로 이동하면 됨.
# MP4 일반: next_box = box_start + box_size
# MP4 예외1: box_size == 1 이면 largesize(64비트) 읽어서 씀.
# MP4 예외2: box_size == 0 이면 부모 박스 끝(또는 파일 끝)까지로 봄.

import sys  # CLI 인자 받으려고 씀.
import os  #경로/파일 처리하려고 씀.
import struct  #바이트를 숫자로 풀어보려고 씀.
import subprocess  # ffmpeg 호출하려고 씀.

# 공통 유틸 함수들임.
def read_u32_le(f):
    return struct.unpack('<I', f.read(4))[0]  # 리틀엔디안 4바이트 읽음.
def read_u32_be(f):
    return struct.unpack('>I', f.read(4))[0]  # 빅엔디안 4바이트 읽음.
def read_u64_be(f):
    return struct.unpack('>Q', f.read(8))[0]  # 빅엔디안 8바이트 읽음.
def fourcc_str(b):
    return b.decode('ascii', errors='ignore')  # FourCC를 문자열로 바꿔둠.
# 1. MP4 파서임. 트랙 식별이랑 오프셋 추적도 같이 함.
MP4_CONTAINERS = {'moov', 'trak', 'edts', 'mdia', 'minf', 'dinf', 'stbl'}  # 자식 박스 들고 있는 컨테이너 목록임.

def parse_mp4(filepath):
    """MP4 박스 쭉 돌면서 코덱 정보 모아봄"""
    print(f"\n{filepath}\n\nmp4 file format\n")  # 지금 보는 파일 경로 먼저 찍음.
    print("-" * 29 + "\n\n# Offset info\n")  # 오프셋 정보 섹션 시작함.

    codec_info = []  # stsd에서 뽑은 코덱 정보 담아둠.
    with open(filepath, 'rb') as f:  # 파일을 바이너리로 엶.
        _parse_mp4_boxes(f, 0, os.path.getsize(filepath), depth=0, codec_info=codec_info)  # 루트부터 재귀로 내려감.

    print("-" * 35 + "\n# Summary\n")  # 마지막 요약 섹션 찍음.
    for name, data in codec_info:  # 모아둔 코덱 정보 순회함.
        print(f"Codec Name (stsd):  {name}")  # 코덱 이름 찍음.
        print(f"Codec data (stsd) {data}\n")  # 코덱 raw 데이터 찍음.

def _parse_mp4_boxes(f, start, end, depth, codec_info):
    """지정 범위 MP4 박스를 재귀로 파싱함"""
    f.seek(start)  # 파싱 시작 위치로 이동함.
    pad = "        " * depth  # depth에 맞춰 들여쓰기 맞춤.

    while f.tell() < end - 8:  # 헤더 8바이트 이상 남아있을 때만 반복함.
        box_start = f.tell()  # 박스 시작 오프셋 잡아둠.
        box_size = read_u32_be(f)  # 32비트 박스 크기 읽음.
        box_type = fourcc_str(f.read(4))  # 박스 타입(FourCC) 읽음.

        if box_size == 1:
            box_size = read_u64_be(f)  # large size면 64비트 크기 다시 읽음.
        box_end = box_start + box_size  # 박스 끝 오프셋 계산함.
        if box_end > end or box_size < 8:
            break  # 범위 벗어나거나 크기 이상하면 중단함.
        data_offset = f.tell()  # 헤더 뒤 데이터 시작 위치 저장함.

        print(f"{pad}{box_type} box start offset: {hex(box_start)}")  # 시작 오프셋 출력함.
        print(f"{pad}{box_type} box size: {hex(box_size)}\n")  # 박스 크기 출력함.

        if box_type in MP4_CONTAINERS:
            _parse_mp4_boxes(f, data_offset, box_end, depth + 1, codec_info)  # 컨테이너면 내부로 더 내려감.

        elif box_type == 'stsd':
            f.seek(data_offset + 8)  # version, flags, entry_count 건너뜀.
            f.read(4)  # entry size 건너뜀.
            entry_type = fourcc_str(f.read(4))  # 샘플 엔트리 타입 읽음.
            f.seek(data_offset + 8)  # stsd payload 시작점으로 다시 감.
            codec_info.append((entry_type, f.read(box_end - f.tell())))  # 코덱 타입이랑 payload 저장함.

        elif box_type == 'hdlr':
            f.seek(data_offset + 8)  # version, flags, pre_defined 건너뜀.
            handler_type = fourcc_str(f.read(4))  # 트랙 핸들러 타입 읽음.
            if handler_type == 'vide':
                print(f"{pad}  => [트랙 정보] 비디오(Video) 트랙임\n")  # 비디오 트랙으로 판별됨.
            elif handler_type == 'soun':
                print(f"{pad}  => [트랙 정보] 오디오(Audio) 트랙임\n")  # 오디오 트랙으로 판별됨.

        elif box_type == 'stco':
            f.seek(data_offset + 4)  # version, flags 건너뜀.
            entry_count = read_u32_be(f)  # 청크 오프셋 개수 읽음.
            print(f"{pad}  => [데이터 위치] 총 {entry_count}개의 미디어 청크 오프셋 기록됨")  # 오프셋 개수 출력함.
            if entry_count > 0:
                sample_count = min(3, entry_count)  # 너무 길어지면 앞 3개만 봄.
                offsets = [hex(read_u32_be(f)) for _ in range(sample_count)]  # 샘플 오프셋 몇 개만 읽음.
                print(f"{pad}  => [데이터 위치] 시작 좌표 샘플: {offsets} ...\n")  # 샘플 오프셋 출력함.

        f.seek(box_end)  # 다음 박스로 가려고 현재 박스 끝으로 점프함.
# 2. AVI 파서임. strh랑 청크 구조 같이 봄.
def parse_avi(filepath):
    """AVI 구조 돌면서 비디오/오디오 청크 모아봄"""
    print(f"\n{filepath}\n\navi file format\n")  # 지금 보는 AVI 파일 경로 찍음.
    v_chunks, a_chunks = [], []  # 비디오/오디오 청크 담을 리스트 준비함.

    with open(filepath, 'rb') as f:  # 파일 바이너리로 엶.
        if f.read(4) != b'RIFF':
            return None, None  # RIFF 아니면 바로 종료함.

        file_data_size = read_u32_le(f)  # RIFF 데이터 크기 읽음.
        if f.read(4) != b'AVI ':
            return None, None  # AVI 식별자 아니면 바로 종료함.

        print(f"file size: {hex(file_data_size + 8)}")  # 전체 파일 크기(헤더 포함) 출력함.
        print(f"file data size: {hex(file_data_size)}\n")  # RIFF data size 출력함.

        _parse_avi_chunks(f, file_data_size + 8, v_chunks, a_chunks, depth=0, inside_movi=False)  # 최상위 청크부터 파싱 돌림.

    return v_chunks, a_chunks  # 모아둔 비디오/오디오 청크 반환함.

def _parse_avi_chunks(f, end_offset, v_chunks, a_chunks, depth, inside_movi):
    """AVI 청크 재귀로 읽으면서 movi 데이터도 모음"""
    pad = "  " * depth  # depth 맞춰 들여쓰기 만듦.

    while f.tell() < end_offset - 8:  # 최소 헤더가 남아있을 때만 반복함.
        c_start = f.tell()  # 청크 시작 위치 저장함.
        c_id = fourcc_str(f.read(4))  # 청크 ID 읽음.
        c_size = read_u32_le(f)  # 청크 크기 읽음.
        data_start = f.tell()  # 청크 데이터 시작 위치 저장함.
        padded_end = data_start + c_size + (c_size % 2)  # 2바이트 정렬 반영해서 끝 위치 계산함.

        if c_id == 'LIST':
            l_type = fourcc_str(f.read(4))  # LIST 타입 읽음.
            print(f"{pad}{l_type} list start offset: {hex(c_start)}")  # LIST 시작 오프셋 출력함.
            print(f"{pad}{l_type} list size: {hex(c_size)}\n")  # LIST 크기 출력함.
            _parse_avi_chunks(
                f,
                padded_end,
                v_chunks,
                a_chunks,
                depth + 1,
                inside_movi=(l_type == 'movi' or inside_movi),
            )  # LIST 내부 청크 재귀로 더 들어감.

        elif c_id == 'strh':
            print(f"{pad}{c_id} start offset: {hex(c_start)}")  # strh 시작 오프셋 출력함.
            print(f"{pad}{c_id} size: {hex(c_size)}")  # strh 크기 출력함.
            if c_size >= 8:
                fcc_type = fourcc_str(f.read(4))  # 스트림 타입 vids/auds 읽음.
                fcc_handler = fourcc_str(f.read(4))  # 핸들러 FourCC 코덱 읽음.
                if fcc_type == 'vids':
                    print(f"{pad}  => [헤더 분석] 비디오 코덱(FourCC): {fcc_handler}")  # 비디오 코덱 출력함.
                elif fcc_type == 'auds':
                    print(f"{pad}  => [헤더 분석] 오디오 코덱(FourCC): {fcc_handler}")  # 오디오 코덱 출력함.
            print()  # 보기 좋게 한 줄 띄움.
            f.seek(padded_end)  # 다음 청크로 가려고 끝 위치로 이동함.

        else:
            print(f"{pad}{c_id} start offset: {hex(c_start)}")  # 일반 청크 시작 오프셋 출력함.
            print(f"{pad}{c_id} size: {hex(c_size)}\n")  # 일반 청크 크기 출력함.

            if inside_movi and c_size > 0 and len(c_id) == 4:
                stream_type = c_id[2:]  # 뒤 2글자로 스트림 종류 판별함.
                if stream_type in ('dc', 'db'):
                    v_chunks.append((data_start, c_size))  # 비디오 청크 위치/크기 저장함.
                elif stream_type == 'wb':
                    a_chunks.append((data_start, c_size))  # 오디오 청크 위치/크기 저장함.

            f.seek(padded_end)  # 다음 청크 시작 위치로 이동함.

# 3. 데이터 추출이랑 페이로드 교차 검증도 해봄.
def extract_avi_streams(filepath, video_chunks, audio_chunks, out_dir='extracted'):
    """AVI에서 비디오/오디오 raw 뽑고 JPG 변환도 해봄"""
    os.makedirs(out_dir, exist_ok=True)  # 출력 폴더 없으면 만듦.
    base = os.path.splitext(os.path.basename(filepath))[0]  # 파일명에서 확장자 뺀 base 이름 구함.

    codec_ext = "h264"  # 기본 비디오 확장자는 h264로 둠.
    ffmpeg_fmt = "h264"  # ffmpeg 입력 포맷 기본값도 h264로 둠.

    if video_chunks:
        with open(filepath, 'rb') as f:  # 원본 파일 열고 첫 비디오 페이로드 확인함.
            f.seek(video_chunks[0][0])  # 첫 비디오 청크 시작 위치로 이동함.
            first_5_bytes = f.read(5)  # 시그니처 판별용 앞 5바이트 읽음.

            print("\n" + "=" * 50)  # 교차 검증 섹션 구분선 찍음.
            if first_5_bytes == b'\x00\x00\x00\x01\x40':
                codec_ext = "h265"  # H.265 시그니처면 확장자 h265로 바꿈.
                ffmpeg_fmt = "hevc"  # H.265 시그니처면 ffmpeg 포맷 hevc로 바꿈.
                print("[포렌식 교차 검증] 실제 Payload에서 H.265(HEVC) 시그니처 식별함")  # H.265 식별 결과 찍음.
            else:
                print("[포렌식 교차 검증] 실제 Payload에서 H.264(AVC) 시그니처 식별함")  # H.264 식별 결과 찍음.
            print("=" * 50 + "\n")  # 교차 검증 섹션 마감선 찍음.

    video_raw_path = os.path.join(out_dir, f"{base}_video.{codec_ext}")  # 비디오 raw 출력 경로 만듦.
    print(f"[추출] 비디오 프레임 수: {len(video_chunks)}")  # 비디오 청크 개수 출력함.
    print(f"[추출] 비디오 raw 저장: {video_raw_path}")  # 비디오 저장 경로 출력함.

    with open(filepath, 'rb') as src, open(video_raw_path, 'wb') as dst:  # 원본/비디오 출력 파일 동시에 엶.
        for offset, size in video_chunks:  # 수집한 비디오 청크 순회함.
            src.seek(offset)  # 원본에서 해당 청크 위치로 이동함.
            dst.write(src.read(size))  # 해당 청크 데이터 읽어서 그대로 씀.

    audio_raw_path = os.path.join(out_dir, f"{base}_audio.raw")  # 오디오 raw 출력 경로 만듦.
    print(f"[추출] 오디오 청크 수: {len(audio_chunks)}")  # 오디오 청크 개수 출력함.
    print(f"[추출] 오디오 raw 저장: {audio_raw_path}")  # 오디오 저장 경로 출력함.

    with open(filepath, 'rb') as src, open(audio_raw_path, 'wb') as dst:  # 원본/오디오 출력 파일 동시에 엶.
        for offset, size in audio_chunks:  # 수집한 오디오 청크 순회함.
            src.seek(offset)  # 원본에서 해당 청크 위치로 이동함.
            dst.write(src.read(size))  # 해당 청크 데이터 읽어서 그대로 씀.

    jpg_path = os.path.join(out_dir, f"{base}_frame_%04d.jpg")  # JPG 출력 파일 패턴 경로 만듦.
    print(f"\n[ffmpeg] {codec_ext.upper()} raw -> JPG 변환 중...\n[ffmpeg] 출력: {jpg_path}")  # ffmpeg 변환 시작 로그 찍음.

    cmd = ['ffmpeg', '-y', '-f', ffmpeg_fmt, '-i', video_raw_path, '-vframes', '10', '-q:v', '2', jpg_path]  # ffmpeg 명령 인자 구성함.
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)  # ffmpeg 실행하고 출력 캡처함.
        if result.returncode == 0:
            print("[ffmpeg] 변환 성공함")  # 종료 코드 0이면 성공임.
        else:
            print(f"[ffmpeg] 변환 실패/경고:\n{result.stderr[-500:] if result.stderr else ''}")  # 실패하면 stderr 끝부분만 찍음.
    except FileNotFoundError:
        print("[ffmpeg] 시스템에서 FFmpeg 명령을 찾을 수 없음")  # ffmpeg 없으면 여기서 안내함.

# 4. 메인임. 시그니처 보고 포맷 판별해서 파서로 넘김.
def main():
    if len(sys.argv) < 2:
        print("Usage: python avi_mp4_parser.py <파일경로>")  # 인자 없으면 사용법 출력함.
        sys.exit(1)  # 잘못 실행된 거라 종료 코드 1로 끝냄.

    filepath = sys.argv[1]  # 첫 번째 인자를 대상 파일 경로로 받음.
    if not os.path.isfile(filepath):
        print(f"오류: 파일을 찾을 수 없습니다 -> {filepath}")  # 파일 없으면 에러 찍음.
        sys.exit(1)  # 파일 없을 때는 오류 종료함.

    with open(filepath, 'rb') as f:  # 시그니처 확인하려고 파일 엶.
        header = f.read(12)  # 포맷 판별용 앞 12바이트 읽음.

    if header[0:4] == b'RIFF' and header[8:12] == b'AVI ':
        print("=> 시스템 판별: AVI 컨테이너 인식 완료함")  # AVI로 판별됐다고 출력함.
        v_chunks, a_chunks = parse_avi(filepath)  # AVI 파서 돌려서 청크 목록 받음.
        if v_chunks is not None:
            extract_avi_streams(filepath, v_chunks, a_chunks)  # AVI 추출/변환 루틴 실행함.

    elif header[4:8] == b'ftyp':
        print("=> 시스템 판별: MP4 컨테이너 인식 완료함")  # MP4로 판별됐다고 출력함.
        parse_mp4(filepath)  # MP4 파서 실행함.

    elif header[0:4] == b'\x00\x00\x00\x01':
        if header[4] == 0x40:
            print("=> 시스템 판별: 컨테이너 없는 H.265임")  # Annex B H.265 raw 스트림임.
        else:
            print("=> 시스템 판별: 컨테이너 없는 H.264임")  # Annex B H.264 raw 스트림임.
        print("파싱은 여기서 종료함")  # 컨테이너가 없어서 여기서 끝냄.

    else:
        print("=> 분석 실패: 지원하지 않는 파일 시그니처임. 정상적인 AVI/MP4가 아님")  # 지원 안 되는 시그니처라고 안내함.
        sys.exit(1)  # 지원 불가 포맷이라 오류 종료함.


if __name__ == '__main__':
    main()  # 스크립트 직접 실행이면 main 호출함.