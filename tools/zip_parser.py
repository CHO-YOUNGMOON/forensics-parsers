import struct
import os # 파일 입출력 및 디렉토리 생성에 필요

# 1. 파일 설정 및 준비
import sys
if len(sys.argv) != 2:
    print("사용법: python zip_parser.py <ZIP 파일>")
    sys.exit(1)
file_path = sys.argv[1]  # 분석할 ZIP 파일 경로를 인자로 받음
out_dir = "CD_Headers" # CD 헤더를 저장할 폴더
os.makedirs(out_dir, exist_ok=True) # 폴더가 없으면 생성, 있으면 무시

with open(file_path, "rb") as f:# ZIP 파일을 바이너리 모드로 열기
    binary_data = f.read()# 전체 파일을 메모리에 읽어서 저장

# LFH(Local File Header) 파싱을 위해 CD에서 얻은 정보를 저장해둘 리스트
local_headers_info = []#리스트로 LFH저장해서 나중에 쓸라고

#EOCD Parsing
eocd_offset = binary_data.rfind(b'\x50\x4B\x05\x06') #rfind->뒤에서 부터 찾아서 거슬러 올라가면서 EOCD 시그니처(50 4B 05 06)를 찾음
if eocd_offset == -1:#EOCD 시그니처가 없으면 오류 메시지 출력 후 종료
    print("EOCD Signature not found.")
    exit()

# EOCD 22바이트 파싱
eocd_data = struct.unpack("<4sHHHHIIH", binary_data[eocd_offset:eocd_offset+22])
#<리틀 엔디언->뒤에서 부터 읽기 4s->4바이트 문자열, H->2바이트 unsigned short, I->4바이트 unsigned int
disk_start = eocd_data[1] #디스크 번호
disk_w_cd = eocd_data[2]    #CD가 있는 디스크 번호
disk_entry = eocd_data[3]#CD 엔트리가 있는 디스크 번호
total_entry = eocd_data[4]#CD 엔트리 수
size_cd = eocd_data[5]#CD 크기
cd_offset = eocd_data[6]#CD 오프셋
comment_len = eocd_data[7]#코멘트 길이

#comment length가 0일 경우 None 출력 
display_comment = "None" if comment_len == 0 else comment_len

print("# File signature (Magic Number): 50 4B 05 06")
print(f"Disk Start Number: {disk_start}")
print(f"Disk # w/cd: {disk_w_cd}")
print(f"Disk Entry: {disk_entry}")
print(f"Total Entry: {total_entry}")
print(f"Size of Central Directory: {size_cd}")
print(f"Central Header Offset: {cd_offset}")#
print(f"Comment Length: {display_comment}")#EOCD에서 얻은 정보를 화면에 출력
print("\n----------------------------------------------------------\n")
print("# Central Directory File header\n") # CD 헤더는 총 46바이트의 고정 크기와 가변 크기의 파일명, 엑스트라 필드, 코멘트로 구성되어 있음

current_offset = cd_offset #CD 헤더의 시작 주소를 오프셋(탐색 기준점)으로 설정

for i in range(total_entry):
    # CD 46바이트 고정 헤더 파싱
    cd_data = struct.unpack("<4sHHHHHHIIIHHHHHII", binary_data[current_offset:current_offset+46])
    #4s->4바이트 문자열, H->2바이트 unsigned short, I->4바이트 unsigned int 422224442222244
    
    #인덱싱 번호로 변수저장
    v_made = cd_data[1]
    v_needed = cd_data[2]
    flags = cd_data[3]
    comp_method = cd_data[4]
    mod_time = cd_data[5]
    mod_date = cd_data[6]
    crc32 = cd_data[7]
    comp_size = cd_data[8]
    uncomp_size = cd_data[9]
    name_len = cd_data[10]
    extra_len = cd_data[11]
    file_comment_len = cd_data[12]
    disk_start_num = cd_data[13]
    int_attr = cd_data[14]
    ext_attr = cd_data[15]
    local_header_offset = cd_data[16]

    # 가변 영역 파싱 (파일명) 고정 헤더(46바이트) 바로 뒷부분에는 파일 이름이 온다 시작점을 현재위치+46으로 설정해서 현재위치+46+파일명 길이 까지 슬라이싱해서 파일명 바이트 추출
    name_bytes = binary_data[current_offset+46 : current_offset+46+name_len]
    
    # 한글, 영어 모두 정상 출력 (UTF-8 시도 후 CP949로 디코딩)
    try:#에러가 나도 프로그램 속행시킴
        filename = name_bytes.decode('utf-8')
    except UnicodeDecodeError:
        filename = name_bytes.decode('cp949') #옛날 한글파일이어도 깨지지 않게 CP949로 디코딩 시도

    # LFH 파싱을 위해 정보 저장 위에서 만들었음
    local_headers_info.append((local_header_offset, filename)) #append->리스트에 로칼헤더현재위치,파일명 저장

    # 화면 출력용 문자열 구성 (예시 텍스트와 동일하게)
    cd_output = (
        f"#{i}.\n"
        f"File signature (Magic Number): 50 4B 01 02\n"
        f"Version made by: {v_made}\n"
        f"Version needed to extract (minimum): {v_needed}\n"
        f"Flags: {flags}\n"
        f"Compression method: {comp_method}\n"
        f"Moditime/Modidate: {mod_time}/{mod_date}\n"
        f"CRC-32 CheckSum: {crc32}\n"
        f"Compressed Size/Uncompressed Size: {comp_size}/{uncomp_size}\n"
        f"File Name Length/Extra Field Length: {name_len}/{extra_len}\n"
        f"File Comment Length: {file_comment_len}\n"
        f"Disk Start Number: {disk_start_num}\n"
        f"Internal Attribute: {int_attr}\n"
        f"External Attribute: {ext_attr}\n"
        f"Local Header: {local_header_offset}\n"
        f"File Name: {filename}\n"
    )
    
    print(cd_output)

    #CD 헤더 Data 영역은 파일 입출력으로 각각 저장
    safe_filename = filename.replace("/", "_").replace("\\", "_") #파일명에 슬래시가 있으면 폴더로 인식해서 저장이 안될 수 있으므로 슬래시를 언더바로 바꿈
    with open(os.path.join(out_dir, f"{safe_filename}_CD.txt"), "w", encoding="utf-8") as wf: #텍스트로 작성
        wf.write(cd_output) #CD 헤더 정보 저장 텍스트로

    # 다음 CD 엔트리로 오프셋 이동
    current_offset += (46 + name_len + extra_len + file_comment_len)

print("----------------------------------------------------------\n")
print("# Local File Header\n")

#  Local File Header Parsing
# CD에서 수집한 오프셋을 바탕으로 LFH 영역으로 점프하여 파싱
for i, (lh_offset, fname) in enumerate(local_headers_info): #enumerate -> 리스트의 인덱스와 값을 동시에 가져옴
    # LFH 30바이트 고정 헤더 파싱
    lh_data = struct.unpack("<4sHHHHHIIIHH", binary_data[lh_offset:lh_offset+30])#
    
    v_needed = lh_data[1]
    flags = lh_data[2]
    comp_method = lh_data[3]
    mod_time = lh_data[4]
    mod_date = lh_data[5]
    crc32 = lh_data[6]
    comp_size = lh_data[7]
    uncomp_size = lh_data[8]
    name_len = lh_data[9]
    extra_len = lh_data[10]

    lh_output = (
        f"#{i}.\n"
        f"File signature (Magic Number): 50 4B 03 04\n"
        f"Version needed to extract (minimum): {v_needed}\n"
        f"Flags: {flags}\n"
        f"Compression method: {comp_method}\n"
        f"Moditime/Modidate: {mod_time}/{mod_date}\n"
        f"CRC-32 CheckSum: {crc32}\n"
        f"Compressed Size/Uncompressed Size: {comp_size}/{uncomp_size}\n"
        f"File Name Length/Extra Field Length: {name_len}/{extra_len}\n"
        f"File Name: {fname}\n"
    )
    
    print(lh_output)