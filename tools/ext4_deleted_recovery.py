import struct
import os
import hashlib

class Ext4DeletedFileScanner:
    def __init__(self, image_path): # EXT4 파일 시스템 이미지 경로를 받아 초기화
        self.image_path = image_path # EXT4 파일 시스템 이미지 경로
        self.f = open(image_path, 'rb')# 이미지 파일을 바이너리 모드로 열기
        
        # 1. 슈퍼블럭 파싱 (모든 계산의 기준점)
        self.parse_superblock()

    def parse_superblock(self):
        """
        [함수 설명]
        디스크의 0x400(1024) 위치에 있는 슈퍼블럭을 읽어 EXT4의 구조 정보를 가져옴.
        블럭 크기, 그룹당 아이노드 개수 등을 알아야 모든 EXT4에서 작동하기 위한 잧치임.
        """
        self.f.seek(1024) # 슈퍼블럭은 1024바이트 오프셋에서 시작
        sb_data = self.f.read(1024)# 슈퍼블럭 데이터 읽기
        
        # s_log_block_size: 블럭 크기 계산을 위한 로그 값
        log_block_size = struct.unpack('<I', sb_data[24:28])[0]
        self.block_size = 1024 << log_block_size  # 공식: 블럭 크기 = 1024 * (2^s_log_block_size)
        
        # s_inodes_per_group: 블럭 그룹당 할당된 아이노드 개수
        self.inodes_per_group = struct.unpack('<I', sb_data[40:44])[0]
        
        # s_inode_size: 아이노드 구조체 하나당 크기 (보통 256바이트)
        self.inode_size = struct.unpack('<H', sb_data[88:90])[0]
        
        # s_blocks_per_group: 그룹당 블럭 개수
        self.blocks_per_group = struct.unpack('<I', sb_data[32:36])[0]

    def get_inode_table_offset(self, group_idx):
        """
        [함수 설명]
        특정 블럭 그룹의 아이노드 테이블이 시작되는 오프셋을 찾음.
        그룹 디스크립터 테이블을 참조하여 동적으로 계산합니다.
        """
        # 그룹 디스크립터 테이블ㅇ느 슈퍼블록 다음 블록부터 시작
        gdt_start = self.block_size if self.block_size > 1024 else 2048
        
        # 각 그룹 디스크립터는 32바이트(32비트 시스템) 또는 64바이트(64비트)
        # 여기서는 표준 32바이트를 기준으로 위치를 찾음
        self.f.seek(gdt_start + (group_idx * 32))
        gdt_data = self.f.read(32)
        
        # bg_inode_table_lo: 아이노드 테이블이 시작되는 블록 번호 (하위 32비트)
        it_block_num = struct.unpack('<I', gdt_data[8:12])[0]
        return it_block_num * self.block_size

    def parse_extent(self, block_data):
        """
        [함수 설명]
        EXT4의 데이터 저장 방식인 엑스텐드 구조를 해독합니다.
        지워진 파일이 실제 디스크의 몇 번 블럭에 저장되어 있는지 리스트로 반환.
        """
        # Extent Header (12바이트)
        magic = struct.unpack('<H', block_data[0:2])[0]
        if magic != 0xF30A: return [] # 엑스텐드 매직 넘버 확인
        
        entries = struct.unpack('<H', block_data[2:4])[0]
        depth = struct.unpack('<H', block_data[6:8])[0]
        
        # depth가 0이면 바로 데이터 블럭 주소가 나옴
        if depth == 0:
            blocks = []
            for i in range(entries):
                # Extent Leaf (12바이트씩) - offset 12부터 시작
                start = 12 + (i * 12)
                leaf = block_data[start:start+12]
                
                # 블럭 개수와 시작 블록 주소 추출
                # len_blocks: 이 엑스텐드가 참조하는 블럭의 개수
                len_blocks = struct.unpack('<H', leaf[4:6])[0]# 이 엑스텐드가 참조하는 블럭의 개수
                start_lo = struct.unpack('<I', leaf[8:12])[0]# 이 엑스텐드가 참조하는 블럭의 시작 번호
                blocks.append((start_lo, len_blocks))# 블럭 번호와 개수의 리스트에 추가
            return blocks# 블럭 번호와 개수의 리스트 반환
        return []

    def scan_deleted_files(self):# 삭제된 파일 스캔 및 복구 시도
        """
        [함수 설명]
        모든 블럭 그룹의 아이노드 테이블을 전수조사하여 삭제된 파일 찾기.
        i_dtime(삭제 시간)이 기록되어 있고, i_links_count가 0인 것이 삭제된 파일의 증거.
        """
        print(f"{'Inode':<8} | {'Size':<10} | {'Deletion Time':<20} | {'Status'}")# 출력 헤더
        print("-" * 60)# 구분선
        
        # 간단하게 첫 번째 그룹(Group 0)만 스캔.
        it_offset = self.get_inode_table_offset(0)# 그룹 0의 아이노드 테이블 시작 오프셋 계산
        
        for i in range(self.inodes_per_group):# 그룹당 아이노드 개수만큼 반복하여 각 아이노드 검사
            self.f.seek(it_offset + (i * self.inode_size))# 각 아이노드의 위치로 이동
            inode_data = self.f.read(self.inode_size)# 아이노드 데이터 읽기
            
            # i_mode (파일 종류), i_links_count (연결 수), i_dtime (삭제 시간)
            mode = struct.unpack('<H', inode_data[0:2])[0]# 파일 모드 (파일 종류 및 권한)
            links_count = struct.unpack('<H', inode_data[26:28])[0]# 링크 수
            dtime = struct.unpack('<I', inode_data[20:24])[0]# 삭제 시간-> 타임스탬프
            size = struct.unpack('<I', inode_data[4:8])[0]# 파일 크기->바이트
            
            # 삭제된 일반 파일 조건: 링크 0, dtime 존재, 파일 모드가 일반 파일(0x8000)
            if dtime != 0 and links_count == 0 and (mode & 0x8000):# 삭제된 일반 파일 조건 확인
                print(f"{i+1:<8} | {size:<10} | {dtime:<20} | DELETED")# 삭제된 파일 정보 출력
                
                # 데이터 블록 주소(Extent) 추출 (offset 40번지부터 60바이트)
                extent_data = inode_data[40:100]# 아이노드에서 엑스텐드 데이터 추출
                block_list = self.parse_extent(extent_data)# 엑스텐드 데이터에서 실제 데이터 블록 위치 추출
                
                if block_list:# 데이터 블록 위치가 존재하면 출력
                    print(f"   ㄴ 데이터 블록 위치: {block_list}")# 데이터 블록 위치 출력
                    # 여기서 파일을 실제로 저장하는 로직을 추가할 수 있습니다.

    def calculate_md5(self, file_data):# 파일 데이터의 MD5 해시값 계산
        """복구한 파일의 MD5 해시값을 대문자로 반환 (플래그 획득용)"""# hashlib 라이브러리를 사용하여 MD5 해시값 계산
        return hashlib.md5(file_data).hexdigest().upper()# MD5 해시값을 대문자로 반환하여 플래그 획득에 사용

# 사용 예시
if __name__ == "__main__":# EXT4 파일 시스템 이미지에서 삭제된 파일을 스캔하여 정보 출력
    import sys
    image = sys.argv[1] if len(sys.argv) > 1 else "ext4.bin"  # 인자가 없으면 ext4.bin 사용
    scanner = Ext4DeletedFileScanner(image)# EXT4 파일 시스템 이미지 경로를 지정하여 스캐너 객체 생성
    scanner.scan_deleted_files()# 삭제된 파일 스캔 및 정보 출력