import struct #바이너리 데이터를 특정 형식으로 해석하기 위한 모듈이다.
import sys #파일을 입력받기 위한 모듈이다.

# MBR을 읽는 함수이다.
def read_mbr(f):
    # 디스크의 맨 처음 0번 오프셋으로 이동한다.
    f.seek(0)
    # MBR은 항상 512바이트 크기이며, 512 바이트를 읽어온다.
    mbr = f.read(512)

    print("# MBR\n")

    #MBR 파티션 테이블은 4개의 엔트리를 가지고 있기에, 4개의 엔트리를 반복문으로 읽어온다.
    for i in range(4):
        #파티션 엔트리 위치를 찾는다.
        entry = mbr[446 + i*16 : 446 + (i+1)*16]

        #파티션 엔트리 구조를 파싱한다.
        (
            boot_flag, #부팅 가능 여부
            start_chs, #시작 CHS 주소
            part_type, #파티션 타입
            end_chs, #끝 CHS 주소
            start_lba, #시작 LBA 주소
            size #파티션 크기 (섹터 수)
        ) = struct.unpack("<B3sB3sII", entry)


        #파티션이 0이면 사용하지 않는 파티션이다. 따라서, 0인 경우는 건너뛴다.
        if part_type == 0:
            continue

        print(f"@ Partition {i}")
        print("Boot Flag:", hex(boot_flag))
        print("Part Type:", hex(part_type))
        print("Starting LBA Addr:", start_lba, "sector")
        print("Size in Sector:", hex(size))
        print()

        #FAT32 파싱을 위해 파티션 시작 위치를 반환한다.
        return start_lba

    return None

#Boot Secter를 읽는 함수이다.
def read_boot_sector(f, lba):
    
    #파티션 시작 위치로 이동한다.
    f.seek(lba * 512)
    #Boot Sector는 항상 512바이트 크기이며, 512 바이트를 읽어온다.
    boot = f.read(512)

    print("-----MBR Check Complete-----\n")
    print("@ Partition 0\n")
    print("#Reserved Area sector")

    #Boot code jump instruction
    jump = boot[0:3]
    #OEM ID
    oem = boot[3:11]

    #Bytes per sector
    bytes_per_sector = struct.unpack("<H", boot[11:13])[0]
    #Sectors per cluster
    sec_per_cluster = boot[13]
    #Reserved sector count
    reserved = struct.unpack("<H", boot[14:16])[0]
    #Sectors per track
    sectors_per_track = struct.unpack("<H", boot[24:26])[0]
    #FAT32 Size (FAT 영역 크기)
    fat_size = struct.unpack("<I", boot[36:40])[0]
    #Root directory 시작 클러스터
    root_cluster = struct.unpack("<I", boot[44:48])[0]

    print("sector:", lba)
    print("Jump Boot Code:", jump.hex(" ").upper())
    print("OEM ID (str/hex):", oem.decode(errors="ignore"), "/", oem.hex(" ").upper())
    print("Bytes Per Sector:", bytes_per_sector)
    print("Sectors Per Cluster:", hex(sec_per_cluster))
    print("Reserved Sector Count:", hex(reserved))
    print("Sector per track:", hex(sectors_per_track))
    print("FAT32 Size:", fat_size)
    print("Root directory cluster offset:", root_cluster, "cluster")

    #필요한 정보를 딕셔너리로 반환한다.
    return {
        "bytes_per_sector": bytes_per_sector,
        "sec_per_cluster": sec_per_cluster,
        "reserved": reserved,
        "fat_size": fat_size,
        "root_cluster": root_cluster,
        "partition_start": lba
    }

#FAT 영역을 계산하는 함수이다.
def calc_fat_area(info):

    #FAT1 시작 위치이다. FAT1은 Reserved Area 다음에 위치한다.
    fat_start = info["partition_start"] + info["reserved"]
    #FAT2 시작 위치이다. FAT2는 FAT1 다음에 위치한다.
    fat2 = fat_start + info["fat_size"]

    #Data 영역 시작 위치이다. Data 영역은 FAT2 다음에 위치한다.
    data_start = fat_start + (info["fat_size"] * 2)

    print("\n# FAT Area")
    print("sector (FAT Area #1):", fat_start)
    print("Backup FAT Area (FAT Area #2):", fat2)

    print("\n# Data Area sector:", data_start)

    return data_start

#Root Directory를 읽는 함수이다.
def read_root_dir(f, info, data_start):

    #root directory는 FAT32에서 클러스터로 관리되며, root_cluster는 root directory의 시작 클러스터 번호이다.
    cluster = info["root_cluster"]

    #root directory의 시작 섹터를 계산한다. 
    sector = data_start + (cluster - 2) * info["sec_per_cluster"]

    #root directory의 시작 섹터로 이동한다.
    f.seek(sector * info["bytes_per_sector"])

    entries = []


    for _ in range(128):
        #디렉터리 엔트리 하나의 바이트는 32 바이트이다.
        entry = f.read(32)
        #파일 이름
        name = entry[0:11]
        #0x00이면 디렉터리가 끝이다.
        if name[0] == 0x00:
            break
        #삭제된 파일을 찾는다.
        if name[0] == 0xE5:
            continue
        #파일의 속성을 찾는다.
        attr = entry[11]

        #Long File Name 엔트리는 건너뛴다.
        if attr == 0x0F:
            continue
        
        #파일 이름
        filename = name[:8].decode(errors="ignore").strip()
        #파일 확장자
        ext = name[8:11].decode(errors="ignore").strip()

        #확장자가 있으면 붙이기
        if ext:
            filename = filename + "." + ext

        entries.append(filename)

    print("\n파일 리스트:", ", ".join(entries))
    print("파일 총 갯수:", len(entries))

#메인 함수이다.
def main():

    #실행 시 파일의 인자를 확인한다
    if len(sys.argv) < 2:
        print("Usage: python fat32_parser.py disk.vhd")
        return

    filename = sys.argv[1]
    
    #디스크 이미지 열기
    with open(filename, "rb") as f:

        #MBR 읽기이다.
        start_lba = read_mbr(f)
        #Boot Sector 읽기이다.
        info = read_boot_sector(f, start_lba)
        #FAT 영역 계산하기이다.
        data_start = calc_fat_area(info)
        #Root Directory 읽기이다.
        read_root_dir(f, info, data_start)

#프로그램을 실행시킨다.
main()