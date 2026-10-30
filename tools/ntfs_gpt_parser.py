import struct #바이너리 데이터를 특정 형식으로 해석하기 위한 모듈이다.
import sys #파일을 입력받기 위한 모듈이다.

#디스크에서 기본적으로 사용하는 섹터 크기이다.
SECTOR_SIZE = 512

#특정 섹터를 읽는 함수이다.
def read_sector(f, sector, count=1):
    #읽을 위치를 이동한다.
    #sector * 512 = 실제 바이트 위치
    f.seek(sector * SECTOR_SIZE)
    #지정한 섹터 수만큼 데이터를 읽어서 반환한다.
    return f.read(count * SECTOR_SIZE)

#Protective MBR을 읽는 함수이다. GPT 디스크에서는 MBR이 존재한다.
def parse_protective_mbr(f):

    print("@ GPT(MBR) - Partition table entry")
    #MBR은 디스크의 첫 번째 섹터 (LBA 0)에 존재한다.
    mbr = read_sector(f, 0)
    #파티션 테이블 엔트리는 446 바이트 이후부터 시작한다.
    entry = mbr[446:462]
    #MBR 파티션 엔트리 구조를 파싱한다.
    boot, start_chs, part_type, end_chs, lba_start, total_sector = struct.unpack(
        "<B3sB3sII", entry
    )
    #부팅 가능 여루를 출력한다.
    print("Boot Indicator:", boot)
    #파티션 시작 LBA 주소를 출력한다.
    print("LBA Start Address:", lba_start, "sector")
    #전체 섹터 수를 출력한다.
    print("Total Sector:", hex(total_sector))
    print()

#GPT Header를 파싱하는 함수이다. 
def parse_gpt_header(f):

    print("@ GPT (MBR) - GPT Header")

    #GPT Header는 LBA 1에 존재한다.
    header = read_sector(f, 1)

    #GPT 시그니처 ("EFI PART")를 읽는다.
    signature = header[0:8]
    #Backup GPT Header 위치
    backup_lba = struct.unpack("<Q", header[32:40])[0]
    #사용 가능한 첫 번째 LBA
    first_usable = struct.unpack("<Q", header[40:48])[0]
    #사용 가능한 마지막 LBA
    last_usable = struct.unpack("<Q", header[48:56])[0]
    #Partition Entry 시작 위치
    part_entry_lba = struct.unpack("<Q", header[72:80])[0]
    #파티션 엔트리 개수
    num_entries = struct.unpack("<I", header[80:84])[0]
    #파티션 엔트리 하나의 크기
    entry_size = struct.unpack("<I", header[84:88])[0]

    print("Signature:", signature)
    print("Backup LBA:", backup_lba)
    print("Starting LBA for partition:", first_usable, "sector")
    print("Ending LBA for partition:", last_usable, "sector")
    print("Number of partition entries:", num_entries)
    print("Size of each entry:", entry_size)
    print()

    #이후에 파티션 테이블을 읽기 위해 반환한다.
    return part_entry_lba, num_entries, entry_size

# GPT 파티션 엔트리를 파싱하는 함수이다.
def parse_partition_entries(f, start_lba, num_entries, entry_size):

    print("@ GPT (MBR) - GPT Partition Entry\n")

    #파티션 엔트리가 시작하는 위치로 이동한다.
    f.seek(start_lba * SECTOR_SIZE)

    partitions = []

    #모든 파티션 엔트리를 반복문으로 읽어온다.
    for i in range(num_entries):

        entry = f.read(entry_size)

        #파티션 시작 LBA
        first_lba = struct.unpack("<Q", entry[32:40])[0]
        #파티션 끝 LBA
        last_lba = struct.unpack("<Q", entry[40:48])[0]
        #파티션 attribute flag
        attr = entry[48:56]
        #파티션 이름 (UTF-16LE로 인코딩되어 있다.)
        name = entry[56:128].decode("utf-16").rstrip("\x00")

        #비어있는 파티션이면 건너뛴다.
        if first_lba == 0:
            continue
        
        partitions.append((first_lba, last_lba, attr, name))

    print("총 파티션 개수:", len(partitions))
    print()
    
    #파티션 정보를 출력한다.
    for idx, p in enumerate(partitions):

        first_lba, last_lba, attr, name = p
        #파티션 크기를 계산한다. (MB 단위로 계산한다.)
        size = (last_lba - first_lba + 1) * SECTOR_SIZE // (1024 * 1024)

        print("- Partition", idx)
        print("Partition start offset:", first_lba, "sector")
        print("Partition end offset:", last_lba, "sector")
        print("Partition Size:", size, "MB")
        #attribute flag 값을 HEX 출력한다.
        print(
            "Partition attribute(flag):",
            " ".join(f"{b:02X}" for b in attr),
        )
        print("Partition Name:", name)
        print("\n----------------------------------------------------------\n")

    return partitions

#VBR을 파싱하는 함수이다.
def parse_vbr(f, partition_start):

    print("데이터 파티션 상세 정보 및 파일 리스트\n")

    print("- Partition 1")
    print("# VBR (Only Basic data partition)")

    #파티션 시작 위치에서 Boot Sector (VBR)를 읽는다.
    vbr = read_sector(f, partition_start)

    #Jump Boot Code
    jump = vbr[0:3]
    #OEM ID
    oem = vbr[3:11]

    #섹터 크기
    bytes_per_sector = struct.unpack("<H", vbr[11:13])[0]
    #클러스터 당 섹터 수
    sectors_per_cluster = struct.unpack("<B", vbr[13:14])[0]

    #MFT  시작 클러스터
    mft_cluster = struct.unpack("<Q", vbr[48:56])[0]
    #MFT Mirror 시작 클러스터
    mftmirr_cluster = struct.unpack("<Q", vbr[56:64])[0]

    print("Jump Boot Code:", jump.hex(" ").upper())
    print(
        "OEM ID (str/hex):",
        oem.decode().strip(),
        "/",
        oem.hex(" ").upper(),
    )

    print("Bytes Per Sector:", bytes_per_sector, "sector")
    print("Sectors Per Cluster:", sectors_per_cluster, "sector")
    print("Start Cluster for $MFT:", mft_cluster, "sector")
    print("Start Cluster for $MFTMirr:", mftmirr_cluster, "sector")
    print()

    #실제 MFT의 LBA 주소를 계산한다.
    mft_lba = partition_start + (mft_cluster * sectors_per_cluster)

    print("# MFT (Master File Table)")
    print("MFT Start offset:", mft_lba, "sector")
    print()

    return mft_lba, sectors_per_cluster

#파일 리스트를 파싱하는 함수이다.
def parse_mft_files(f, mft_lba):

    file_list = []

    #MFT 시작 위치로 이동한다.
    f.seek(mft_lba * SECTOR_SIZE)

    #최대 1024개의 MFT 엔트리를 검사한다.
    for i in range(1024):

        #MFT 엔트리 하나의 크기는 1024 바이트이다.
        entry = f.read(1024)

        #"FILE" 시그니처를 확인한다.
        if entry[0:4] != b"FILE":
            continue
        
        #Attribute 시작 위치이다.
        attr_offset = struct.unpack("<H", entry[20:22])[0]

        offset = attr_offset

        #Attribute를 반복문으로 읽어온다.
        while True:
            #Attribute Type을 읽는다.
            attr_type = struct.unpack("<I", entry[offset:offset + 4])[0]

            #0xFFFFFFFF는 Attribute의 끝을 나타내는 값이다.
            if attr_type == 0xFFFFFFFF:
                break
            
            #Attribute의 길이를 읽는다.
            attr_len = struct.unpack("<I", entry[offset + 4:offset + 8])[0]

            #FILE_NAME Attribute (0x30)인 경우 파일 이름을 추출한다.
            if attr_type == 0x30:

                #파일 이름을 추출한다. (UTF-16로 인코딩되어 있다.)
                name_len = entry[offset + 88]
                name = entry[offset + 90: offset + 90 + name_len * 2].decode("utf-16")

                file_list.append(name)
                break
            
            #다음 Attribute로 이동한다.
            offset += attr_len

    print("파일리스트:", ", ".join(file_list))
    print("파일 총 갯수:", len(file_list))


#메인 함수이다.
def main():

    #실행 시 파일의 인자를 확인한다
    filename = sys.argv[1]

    #디스크 이미지 열기
    with open(filename, "rb") as f:

        #MBR 읽기이다.
        parse_protective_mbr(f)

        #GPT Header 읽기이다.
        part_lba, num, size = parse_gpt_header(f)

        #GPT Partition Entry 읽기이다.
        partitions = parse_partition_entries(f, part_lba, num, size)

        #데이터 파티션의 VBR과 MFT를 읽어서 파일 리스트를 출력한다.
        for p in partitions:
            if "Basic data" in p[3]:
                #MFT에서 파일 이름을 추출한다.
                mft_lba, spc = parse_vbr(f, p[0])
                parse_mft_files(f, mft_lba)
                break

#프로그램을 실행시킨다.
if __name__ == "__main__":
    main()