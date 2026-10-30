import struct
import os
import sys
""""
이 코드는 먼저 입력받은 디스크 이미지 파일(.001)의 앞부분을 스캔하여 
NTFS "시그니처(제일 중요)"를 찾아 파티션의 시작점인 VBR(볼륨 부트 레코드)의 위치를 확보한 뒤
VBR 내부에 기록된 설정값(섹터 및 클러스터 크기, MFT 시작 클러스터 번호)을 조합하여 
디스크의 핵심 장부인 MFT(마스터 파일 테이블)의 실제 물리적 주소를 계산
이후 해당 주소로 이동하여 1024바이트 크기의 MFT 레코드들을 차례대로 탐색하면서
오프셋 0x16 위치의 플래그 값이 '삭제됨(0x00)'인 레코드만 선별하고
 그 내부의 $FILE_NAME 속성(0x30)을 파싱하여 숨겨진 파일의 진짜 이름을 디코딩해 화면에 출력하는 순서로 진행
"""""

def main():#메인함수는 디스크 이미지(.001)를 입력받아 NTFS 파티션을 찾고 MFT(마스터 파일 테이블)를 분석하여 삭제된 파일의 이름을 추출
    
    print("="*60)#프로그램 제목과 간단한 설명을 출력
    print("      [Digital Forensic Tool] NTFS Deleted File Parser (Auto Target)")#프로그램 제목과 간단한 설명을 출력
    print("="*60)

    if len(sys.argv) >= 2:#명령행 인자로 디스크 이미지 파일 경로가 제공되었는지 확인.경로 확인하고나 없으면 에러 출력
        img_path = sys.argv[1]#명령행 인자로 제공된 디스크 이미지 파일 경로를 img_path 변수에 저장
    else:
        img_path = input("\n[?] 분석할 .001 파일 이름을 입력하세요: ").strip('"').strip("'")#분석할 .001 파일 이름을 입력하도록 요청하고 따옴표 제거 해서 복붙하기 편하게

    if not os.path.exists(img_path):#파일 못찾은 케이스
        print(f"\n[!] 🚨 에러: 파일을 찾을 수 없습니다.")
        return

    print(f"\n[*] 타겟 확인 완료: {img_path}")#파일 찾으면 시작
    print("[*] 디스크 내부 NTFS 파티션을 스캔합니다...\n")#

    try:
        with open(img_path, "rb") as f:
            # 1. VBR(NTFS 파티션 시작점) 자동 탐색 로직 추가
            f.seek(0)
            chunk = f.read(50 * 1024 * 1024)  # 앞부분 50MB 스캔 
            
            # NTFS의 고유 시그니처인 'NTFS    ' 글자를 찾기 위해
            vbr_idx = chunk.find(b'NTFS    ')
            if vbr_idx == -1:
                print("[!] 에러: 이 파일 안에서 NTFS 파티션을 찾을 수 없습니다.")
                return
                
            vbr_offset = vbr_idx - 3 # 시그니처 위치를 통해 파티션 시작점(VBR) 계산
            print(f"[*] NTFS 파티션 발견! (위치: {hex(vbr_offset)})")
            
            # 2. VBR 파싱 및 MFT 위치 계산
            f.seek(vbr_offset)#VBR의 시작점으로 이동하여 VBR의 내용을 읽음
            vbr = f.read(512)#VBR에서 섹터,클러스터 크기, MFT 시작 클러스터 번호 등의 정보를 읽어서 변수에 저장
            bps = struct.unpack('<H', vbr[0x0B:0x0D])[0] #VBR에서 섹터 크기(BPS)를 읽어서 bps 변수에 저장
            spc = struct.unpack('<B', vbr[0x0D:0x0E])[0] #VBR에서 클러스터당 섹터 수(SPC)를 읽어서 spc 변수에 저장
            mft_lcn = struct.unpack('<Q', vbr[0x30:0x38])[0] #VBR에서 MFT 시작 클러스터 번호(LCN)를 읽어서 mft_lcn 변수에 저장
            
            # 파티션 시작점 + (클러스터 번호 * 섹터크기 * 클러스터당 섹터)=NTFS MFT의 실제 물리적 주소 계산
            mft_offset = vbr_offset + (mft_lcn * bps * spc)# VBR에서 읽은 정보로 MFT의 실제 위치 계산
            print(f"[*] 진짜 MFT 시작 지점: {hex(mft_offset)}")#MFT 시작 지점 출력하여 사용자에게 MFT가 어디에 위치하는지 알려줌
            print("-" * 60)#MFT 레코드 탐색을 시작하기 전에 헤더를 출력하여 결과를 보기 좋게 정리함
            print(f"{'MFT Index':<10} | {'Status':<12} | {'File Name'}")#MFT 레코드 탐색 결과를 출력하기 위한 헤더로, MFT 인덱스, 상태(삭제 여부), 파일 이름을 표시하는 열을 정의함
            print("-" * 60)# MFT헤더 출력

            # 3. MFT 레코드 탐색 및 삭제 파일 추출
            for i in range(2000):#MFT 레코드 2000개 탐색
                f.seek(mft_offset + (i * 1024))#MFT 레코드의 크기는 일반적으로 1024바이트이므로, MFT 시작 지점에서 i번째 레코드의 위치->읽음
                entry = f.read(1024)#MFT 레코드의 첫 4바이트가 'FILE'이 아니면 넘어감
                if entry[:4] != b'FILE': continue#MFT 레코드의 오프셋 0x16 위치에 있는 플래그 값을 읽어서 삭제된 파일인지 확인
                
                flags = struct.unpack('<H', entry[0x16:0x18])[0]#삭제면->네임 플레그 읽어서 flags 변수에 저장(0x30)
                if flags == 0x00: # 삭제된 파일 확인(삭제 됐다는 뜻)
                    fn_idx = entry.find(b'\x30\x00\x00\x00')#$FILE_NAME 속성(0x30)을 찾아서 해당 속성의 위치를 확보
                    if fn_idx != -1:
                        name_len = entry[fn_idx + 88]#이름 len이름 변수에 저장
                        name_raw = entry[fn_idx + 90 : fn_idx + 90 + (name_len * 2)]#name_raw에 이름 2바이트씩 저장
                        filename = name_raw.decode('utf-16le', errors='ignore')#name_raw를 유니코드로 디코딩하여 실제 파일 이름을 얻어서 filename 변수에 저장
                        
                        if not filename.startswith('$'):#시스템 파일이 아닌 경우에만 출력
                            print(f"{i:<10} | {'DELETED':<12} | {filename}")#어떤 파일이 삭제되어있는지 알려줌
            print("-" * 60)
            print("[*] 수색 완료!")
            
    except Exception as e:
        print(f"[!] 에러 발생: {e}")

if __name__ == "__main__":
    main()