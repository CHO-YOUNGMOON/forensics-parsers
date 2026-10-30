# 파일 경로를 입력
import sys
if len(sys.argv) != 2:
    print("사용법: python png_parser.py <PNG 파일>")
    sys.exit(1)
file_path = sys.argv[1]  # 분석할 PNG 파일 경로를 인자로 받음

# 'rb' 모드로 파일 열기 read binary
with open(file_path, 'rb') as f: #rb는 파일의 바이트를 그대로 읽음->PNG 파일은 텍스트가 아니라 바이너리 데이터로 구성되어 있기 때문에
    binary_data = f.read() # 파일의 모든 바이너리 데이터를 읽음 

    #시그니처 출력
    signature = binary_data[:8]    # 앞의 8바이트(PNG 시그니처)만 잘라서 16진수로 출력하기->시그니쳐는 첫 8바이트이기 떄문
    print("16진수 출력:", signature.hex().upper()) #바이트->16진수 변환,대문자 변환(한 눈에 보기 쉽게)

    print(hex(binary_data[0])) # 첫 번째 바이트를 16진수로 출력하기->PNG 시그니처의 첫 번째 바이트는 항상 0x89

import os #파일 시스템 불러오기

out_dir = "chunks_out" #분해한 청크 저장할 디렉 이름
os.makedirs(out_dir, exist_ok=True)#디렉토리가 이미 존재해도 에러 없이 넘어가도록

#청크(길이,타입,데이터,CRC) 분석-빅 엔디언 이므로 순서대로 분석
#길이-offset 8~11, 타입-offset 12~15, 데이터-타입 다음부터 길이만큼, CRC-데이터 다음 4바이트
import struct #바이트->숫자로 변환하기 위해 설정
import zlib #CRC 계산하기 위해 설정

offset = 8 #시그니처 다음부터 청크가 시작되므로 offset을 8로 설정 인덱스 8 9번째 바이트부터
chunk_index = 0

print("\n[ALL CHUNKS DUMP]")

while True: #break로 루프 탈출할 때까지 계속 반복

    if offset + 12 > len(binary_data): #최소 청크 크기(길이 4 + 타입 4 + CRC 4)가 남아있는지 확인 아니면 루프 탈출
        break
    #청크 길이
    length = struct.unpack(">I", binary_data[offset:offset+4])[0] #청크 길이 읽기->4바이트를 빅 엔디언으로 해석하여 정수로 변환
    #빅 엔디언->PNG는 순서대로 읽는 방식인 빅 엔디언 사용 I는 unsigned int(4바이트) 의미, >는 빅 엔디언을 나타냄 [0]은 튜플 중 첫번째만 가져옴

    #청크 타입
    chunk_type_bytes = binary_data[offset+4:offset+8] #4바이트 다음부터 타입임 ascii->읽어온 4바이트를 알파벳으로 읽기 쉽게 바꿈
    chunk_type = chunk_type_bytes.decode("ascii", errors="replace")#ascii->읽어온 4바이트를 알파벳으로 읽기 쉽게 바꿈

    data_start = offset + 8 #데이터는 타입 다음부터 시작하므로 offset + 8로 설정
    data_end = data_start + length #데이터는 길이만큼 이어지므로 data_start + length로 설정

    if data_end + 4 > len(binary_data): #청크 데이터 뒤에 crc 4바이트 있어야 하는데 없으면 멈추게 
        break

    chunk_data = binary_data[data_start:data_end] #청크 데이터 시작부터 끝까지 읽어서 chunk_data에 저장

    crc_read = struct.unpack(">I", binary_data[data_end:data_end+4])[0] #crc는 data다음 4바이트->빅 엔디언으로 읽어서
    crc_calc = zlib.crc32(chunk_type_bytes + chunk_data) & 0xffffffff #CRC 계산->청크 타입과 데이터로 CRC 계산, & 0xffffffff는 결과를 32비트로 제한하여 음수 방지

    crc_ok = (crc_calc == crc_read) #우리 값이랑 파일에 적힌 값 같다=>무결성 검증 성공

    print(f"{chunk_index:03d}  {chunk_type}  len={length}  CRC={'OK' if crc_ok else 'BAD'}") #청크 인덱스, 타입, 길이, CRC 검증 결과 출력
    #성궁 ok 아니면 bad

    chunk_bytes = ( #변환했던 값들을 다시 바이트로 복원해서-> 청크 파일로 저장
        struct.pack(">I", length) +
        chunk_type_bytes +
        chunk_data +
        struct.pack(">I", crc_read)
    )

    filename = f"{chunk_index:03d}_{chunk_type}.chunk"
    with open(os.path.join(out_dir, filename), "wb") as wf: #wb->바이너리 쓰기 모드로 청크 파일 저장
        wf.write(chunk_bytes)

    if chunk_type == "IHDR" and length == 13: #필수 청크 중 하나인 IHDR 길이=13
        width = struct.unpack(">I", chunk_data[0:4])[0] #4바이트 넓이
        height = struct.unpack(">I", chunk_data[4:8])[0]#4바이트 높이
        bit_depth = chunk_data[8]#1바이트 비트 깊이->8번째 칸은 색상 깇이 
        color_type = chunk_data[9]#1바이트 색상 유형 ->9번째는 색상 타입

        color_map = {#딕셔너리로 미리 숫자와 색상 유형 매핑
            0: "Grayscale",
            2: "Truecolor (RGB)",
            3: "Indexed-color (Palette)",
            4: "Grayscale + Alpha",
            6: "Truecolor + Alpha (RGBA)",
        }

        print(f"    -> {width}x{height}, bit_depth={bit_depth}")
        print(f"    -> ColorType={color_type} ({color_map.get(color_type,'Unknown')})")

    offset = data_end + 4 #다음 청크로 이동 오프셋을 데이터 끝에서 +4인 CRC 다음으로 설정
    chunk_index += 1 #다음 청크라는 뜻

    if chunk_type == "IEND": #청크 끝을 의미하는 IEND 만나면 루프 탈출
        break

    